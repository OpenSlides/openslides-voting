from decimal import Decimal

from django.conf import settings
from openslides.assignments.models import AssignmentOption
from openslides.users.models import User
from openslides.utils.autoupdate import inform_changed_data, inform_deleted_data

from .models import (
    AssignmentAbsenteeVote,
    MotionAbsenteeVote,
    AssignmentPollBallot,
    MotionPollBallot,
    VotingShare,
    VotingPrinciple,
)


def find_authorized_voter(delegate, proxies=None):
    """
    Find the authorized voter of a delegate by recursively stepping through the proxy chain.

    :param delegate: User object
    :param proxies: List of proxy IDs found so far, used to eliminate circular references
    :return: authorized user (the last one in the proxy chain)
    """
    if hasattr(delegate, 'votingproxy'):
        representative = delegate.votingproxy.proxy
        if proxies is None:
            proxies = []
        elif representative.id in proxies:
            # We have a circular reference. Delete the voting proxy to fix it.
            # TODO: Log circular ref error and/or notify user.
            delegate.votingproxy.delete()
            return delegate

        # Add voter id to proxies list.
        proxies.append(delegate.id)

        # Recursively step through the proxy chain.
        return find_authorized_voter(representative, proxies)

    return delegate


def get_admitted_delegates(principle, keypad=False, *order_by):
    """
    Returns a dictionary {<voter_id>: [<delegate_id>]} of admitted delegates.
    Key is the user id of an authorized voter.
    Value is a list of user ids of all delegates represented by the voter, i.e. his mandates
    which may or may not include the voter himself.

    :param principle: Category ID or None.
    :param keypad: True if authorized voter must have a keypad assigned to.
    :param order_by: User fields the list should be ordered by.
    :return: int, dictionary
    """
    # Get delegates who have voting rights (shares) for the given principle.
    # admitted: key: voter id, value: list of delegate ids, i.e. the voter's mandates
    admitted = {}
    qs_delegates = query_admitted_delegates(principle)
    if order_by:
        qs_delegates = qs_delegates.order_by(*order_by)

    # Only admit those delegates whose authorized voter is present with keypad assigned.
    count = 0
    for delegate in qs_delegates.select_related('votingproxy', 'keypad'):
        auth_voter = find_authorized_voter(delegate)
        if auth_voter and auth_voter.is_present and (not keypad or hasattr(auth_voter, 'keypad')):
            key = auth_voter.id
            if key in admitted:
                admitted[key].append(delegate.id)
            else:
                admitted[key] = [delegate.id]
            count += 1

    return count,  admitted


def query_admitted_delegates(principle=None):
    """
    Returns a queryset of admitted delegates.

    Admitted delegates are users belonging to the Delegates group (default id is
    2), AND who have ANY voting rights (shares) if voting shares exist, AND who
    have voting rights for a given voting principle (principle_id).

    :param principle: Principle or None.
    :return: queryset
    """
    delegate_group_id = getattr(settings, 'DELEGATE_GROUP_ID', 2)
    qs = User.objects.filter(groups=delegate_group_id)
    if VotingShare.objects.exists():
        qs = qs.filter(shares__shares__gt=0).distinct()  # distinct is required to eliminate duplicates
    if principle:
        qs = qs.filter(shares__principle=principle)
    return qs


class BaseBallot:
    """
    Base class managing poll ballots for different ballot types.
    """

    def __init__(self, poll, principle=None):
        """
        Creates a Ballot instance for a given poll object and voting principle.

        :param poll: Poll object
        :param principle: Voting principle
        """
        self.poll = poll
        self.principle = principle
        self.admitted_delegates = self._query_admitted_delegates()
        self.updated = 0

    def delete_ballots(self):
        """
        Deletes all ballot objects of the current poll. Returns the number of ballots deleted.
        """
        raise NotImplementedError()

    def create_absentee_ballots(self):
        """
        Creates or updates ballot objects for all voting delegates who have an absentee vote registered.
        Returns the number of absentee ballots created.
        """
        raise NotImplementedError()

    def get_next_result_token(self):
        """
        Returns the next result token for this poll.
        """
        raise NotImplementedError()

    def register_vote(self, vote, voter=None, result_token=0):
        """
        Register a vote and all proxy votes by creating MotionPollBallot objects for the voter and any delegate
        represented by the voter.

        A vote is registered whether or not a proxy exists! The rule is not to assign a keypad to a
        delegate represented by a proxy but we don't enforce this rule here.

        Ballot objects will not be created for any delegate who submitted an absentee vote.

        :param vote: Vote, typically 'Y', 'N', 'A'
        :param voter: User or None for anonymous user
        :param result_token: Token
        :return: Number of ballots created or updated.
        """
        self.updated = 0
        self._register_vote_and_proxy_votes(vote, voter, result_token)
        return self.updated

    def count_votes(self):
        """
        Counts the votes of all ballot objects for the given poll. The returned format
        depends heavily of the actual ballot and poll. Look in the docstrings of the child
        classes to get mor information. These results always have to be handled separately!
        """
        raise NotImplementedError()

    def pseudo_anonymize_votes(self):
        """
        Deletes all user references for all ballots for this poll.
        """
        raise NotImplementedError()

    def _query_admitted_delegates(self):
        """
        Returns a query set of admitted delegate ids. Excludes delegates who cast an absentee vote.
        """
        raise NotImplementedError()

    def _register_vote_and_proxy_votes(self, vote, voter, result_token):
        """
        Helper function that recursively creates ballots for a voter and his mandates.
        """
        self._create_ballot(vote, voter, result_token)
        if voter:
            for proxy in voter.mandates.all():
                self._register_vote_and_proxy_votes(vote, proxy.delegate, result_token)

    def _create_ballot(self, vote, delegate=None, result_token=0):
        """
        Helper function that creates or updates a poll ballot.
        """
        raise NotImplementedError()


class MotionBallot(BaseBallot):
    """
    Creates, deletes, updates MotionPollBallot objects for a given MotionPoll object.
    """

    def delete_ballots(self):
        """
        Deletes all motion poll ballots of the current poll.

        :return: Number of ballots deleted.
        """
        deleted = []
        collection_string = MotionPollBallot.get_collection_string()
        for pk in MotionPollBallot.objects.filter(poll=self.poll).values_list('pk', flat=True):
            deleted.append((collection_string, pk))
        self.updated, _ = MotionPollBallot.objects.filter(poll=self.poll).delete()
        inform_deleted_data(deleted)
        return self.updated

    def create_absentee_ballots(self):
        """
        Creates or updates motion poll ballots all voting delegates who have an absentee vote registered.
        Objects are created even if the delegate is present or whether or not a proxy is present.

        :return: Number of ballots created or updated.
        """
        # Allow only absentee votes of admitted delegates.
        admitted_delegates = query_admitted_delegates(self.principle)

        # Query absentee votes for given motion.
        qs_absentee_votes = MotionAbsenteeVote.objects.filter(motion=self.poll.motion, delegate__in=admitted_delegates)

        self.updated = 0
        ballots = []
        delegate_ids = []
        for absentee_vote in qs_absentee_votes:
            # Update or create ballot instance.
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=absentee_vote.delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=absentee_vote.delegate)
            mpb.vote = absentee_vote.vote
            mpb.result_token = 0
            if mpb.pk:
                mpb.save(skip_autoupdate=True)
            else:
                ballots.append(mpb)
            delegate_ids.append(mpb.delegate.id)
            self.updated += 1

        # Bulk create ballots.
        MotionPollBallot.objects.bulk_create(ballots)

        # Trigger auto-update.
        created_ballots = MotionPollBallot.objects.filter(poll=self.poll, delegate_id__in=delegate_ids)
        inform_changed_data(created_ballots)

        return self.updated

    def get_next_result_token(self):
        """
        Returns the next result token for this poll.
        """
        used_tokens = MotionPollBallot.objects.filter(poll=self.poll).values_list('result_token', flat=True)
        return MotionPollBallot.get_next_result_token(used_tokens)

    def count_votes(self):
        """
        Counts the votes of all MotionPollBallot objects for the given poll.
        
        The result is a dict with values for yes, no and abstain, casted, valid and invalid. 
        The values for casted and valid are equal, the values for invalid are zero.
        Each entry in the result dict is a list with two entries: [heads, shares]. 
        For anonymous votes shares are  set to 1.
        
        :return result dict.
        """
        # Convert the ballots into a list of (delegate_id, vote) tuples.
        # Example: [(1, 'Y'), (2, 'N')]
        votes = MotionPollBallot.objects.filter(poll=self.poll).values_list('delegate', 'vote')

        shares = None
        if self.principle:
            # Create a dict (key: delegate, value: shares).
            # Example: {1: Decimal('1.000000'), 2: Decimal('45.120000')}
            voting_shares = VotingShare.objects.filter(principle=self.principle)
            shares = dict(voting_shares.values_list('delegate', 'shares'))

        # Sum up the votes.
        result = {
            'Y': [0, Decimal(0)],  # [heads, shares]
            'N': [0, Decimal(0)],
            'A': [0, Decimal(0)],
            'casted': [0, Decimal(0)],
            'valid': [0, Decimal(0)],
            'invalid': [0, Decimal(0)]
        }
        for delegate_id, vote in votes:
            if not delegate_id:
                # This is for anonymous votes.
                delegate_share = 1
            else:
                try:
                    delegate_share = shares[delegate_id] if shares else 1
                except KeyError:
                    # Occurs if voting share was removed after delegate cast a vote.
                    continue

            result[vote][0] += 1
            result[vote][1] += delegate_share
            result['casted'][0] += 1
            result['casted'][1] += delegate_share
        result['valid'] = result['casted']

        # TODO NEXT: Add 'not voted abstains' option.
        return result

    def pseudo_anonymize_votes(self):
        """
        Delete all user references for all ballots for this poll.
        """
        # TODO: bulk update
        ballots = MotionPollBallot.objects.filter(poll=self.poll)
        for mpb in ballots:
            mpb.delegate = None
            mpb.save()

    def _query_admitted_delegates(self):
        """
        Returns a query set of admitted delegate ids. Excludes delegates who cast an absentee vote.
        """
        qs = query_admitted_delegates(self.principle).exclude(motionabsenteevote__motion=self.poll.motion)
        return qs.values_list('id', flat=True)

    def _create_ballot(self, vote, delegate=None, result_token=0):
        """
        Creates or updates a motion poll ballot.
        """
        if not delegate:
            # Anonymous delegate
            mpb = MotionPollBallot(poll=self.poll)
        elif delegate.id in self.admitted_delegates:
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=delegate)
        else:
            # Delegate not admitted.
            return

        mpb.vote = vote
        mpb.result_token = result_token
        mpb.save()
        self.updated += 1


class AssignmentBallot(BaseBallot):
    """
    Creates, deletes, updates AssignmentPollBallot objects for a given AssignmentPoll object.
    For more docstring read the descriptions in BaseBallot.
    """
    def delete_ballots(self):
        """
        Deletes all AssignmentPollBallot objects of the current poll.
        """
        deleted = []
        collection_string = AssignmentPollBallot.get_collection_string()
        for pk in AssignmentPollBallot.objects.filter(poll=self.poll).values_list('pk', flat=True):
            deleted.append((collection_string, pk))
        deleted_count, _ = AssignmentPollBallot.objects.filter(poll=self.poll).delete()
        inform_deleted_data(deleted)
        return deleted_count

    def create_absentee_ballots(self, principle=None):
        """
        Creates or updates all assignment poll ballots for every admitted delegate that has an
        absentee vote registered. Returns the amount of absentee votes.
        """

        # TODO: This is currently unsupported!!
        return 0

        """
        # Allow only absentee votes of admitted delegates.
        admitted_delegates = query_admitted_delegates(principle=principle)

        # Query absentee votes for given motion.
        absentee_votes = AssignmentAbsenteeVote.objects.filter(assignment=self.poll.assignment).filter(delegate__in=admitted_delegates)

        ballots_to_create = []
        delegate_ids = []
        candidates_count = self.poll.options.count()
        for absentee_vote in absentee_votes.all():
            # Check, if the absentee vote matches the pollmethod
            vote = absentee_vote.vote
            if self.poll.pollmethod == 'votes':
                try:
                    vote = int(vote)
                except:
                    continue  # skip this invalid vote
                if vote < 1 or vote > candidates_count:
                    continue
            elif vote not in [s.upper() for s in self.poll.pollmethod]:
                continue

            vote = {
                'value': vote,
            }

            # Update or create ballot instance.
            try:
                mpb = AssignmentPollBallot.objects.get(poll=self.poll, delegate=absentee_vote.delegate)
            except AssignmentPollBallot.DoesNotExist:
                mpb = AssignmentPollBallot(poll=self.poll, delegate=absentee_vote.delegate, result_token=0)
            mpb.vote = vote
            if mpb.pk:
                mpb.save(skip_autoupdate=True)
            else:
                ballots_to_create.append(mpb)
            delegate_ids.append(mpb.delegate.id)

        # Bulk create ballots.
        AssignmentPollBallot.objects.bulk_create(ballots_to_create)

        # Trigger auto-update.
        created_ballots = AssignmentPollBallot.objects.filter(poll=self.poll, delegate_id__in=delegate_ids)
        inform_changed_data(created_ballots)

        return len(delegate_ids)
        """

    def get_next_result_token(self):
        """
        Returns the next result token for this poll.
        """
        used_tokens = AssignmentPollBallot.objects.filter(poll=self.poll).values_list('result_token', flat=True)
        return MotionPollBallot.get_next_result_token(used_tokens)

    def count_votes(self):
        """
        Counts all votes for all AssignmentPollBallots for the given poll. The result depends
        on the used pollmethod:
        YNA/YN:
        result = {
            <candidate_id_1>: {
                'Y': [<heads>, <shares>],
                'N': [<heads>, <shares>],
                'A': [<heads>, <shares>],
            },
            ...
            'casted': [<heads>, <shares>],
            'valid': [<heads>, <shares>],
            'invalid': [<heads>, <shares>],
        }
        (For YN the abstain-part is leaved out)

        VOTES:
        result = {
            <candidate_id_1>: [<heads>, <shares>],
            ...
            'casted': [<heads>, <shares>],
            'valid': [<heads>, <shares>],
            'invalid': [<heads>, <shares>],
        }

        This function expects the right vote values for the poll method.
        Just the ballot are counted, that does not have a user or the user must have shares >0.
        """
        votes = AssignmentPollBallot.objects.filter(poll=self.poll)

        shares = None
        # try to find a voting principle
        principle = VotingPrinciple.objects.filter(assignments=self.poll.assignment).first()
        if principle is not None:
            # Create a dict (key: delegate, value: shares).
            # Example: {1: Decimal('1.000000'), 2: Decimal('45.120000')}
            voting_shares = VotingShare.objects.filter(principle=principle)
            shares = dict(voting_shares.values_list('delegate', 'shares'))

        options = AssignmentOption.objects.filter(poll=self.poll).order_by('weight').all()
        pollmethod = self.poll.pollmethod

        result = {
            'casted': [0, Decimal(0)],
            'valid': [0, Decimal(0)],
            'invalid': [0, Decimal(0)]
        }

        if pollmethod in ('yn', 'yna'):
            for option in options:
                result[str(option.candidate.id)] = {
                    'Y': [0, Decimal(0)],  # [heads, shares]
                    'N': [0, Decimal(0)],
                }
                if pollmethod == 'yna':
                    result[str(option.candidate.id)]['A'] = [0, Decimal(0)]
        else:  # votes
            for option in options:
                result[str(option.candidate.id)] = [0, Decimal(0)]

        # Sum up the votes.
        for vote in votes:
            if vote.delegate is None:
                delegate_share = 1
            else:
                try:
                    delegate_share = shares[vote.delegate.pk] if shares else 1
                except KeyError:
                    # Occurs if voting share was removed after delegate cast a vote.
                    continue

            if pollmethod in ('yn', 'yna'):
                # count every vote for each candidate
                for candidate_id, value in vote.vote.items():
                    result[candidate_id][value][0] += 1
                    result[candidate_id][value][1] += delegate_share
            else:
                result[vote.vote][0] += 1
                result[vote.vote][1] += delegate_share
            result['casted'][0] += 1
            result['casted'][1] += delegate_share
        result['valid'] = result['casted']

        return result

    def _create_ballot(self, vote, delegate=None, result_token=0, proxy_protected=None, skip_protected=False):
        """
        Helper function to actually create or update a ballot.
        """
        created = False
        if delegate is not None:
            try:
                apb = AssignmentPollBallot.objects.get(poll=self.poll, delegate=delegate)
            except AssignmentPollBallot.DoesNotExist:
                apb = AssignmentPollBallot(poll=self.poll, delegate=delegate)
                created = True
        else:
            apb = AssignmentPollBallot(poll=self.poll)
            created = True

        if skip_protected and apb.proxy_protected:
            return apb, False

        apb.vote = vote
        apb.result_token = result_token
        if proxy_protected is not None:
            apb.proxy_protected = proxy_protected
        apb.save()
        return apb, created
