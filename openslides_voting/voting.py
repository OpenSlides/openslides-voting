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
    Keypad,
)


def find_authorized_voter(delegate):
    """
    Find the authorized voter of a delegate by stepping through the proxy chain.

    :param delegate: User object
    :return: authorized user (the last one in the proxy chain)
    """
    # List of proxy IDs found so far, used to eliminate circular references
    proxies = []
    # NOTE: Function might be slow with many db hits.
    while hasattr(delegate, 'votingproxy'):
        representation = delegate.votingproxy.proxy
        if representation.id in proxies:
            # We have a circular reference. Delete the voting proxy to fix it.
            # TODO: Log circular ref error and/or notify user.
            delegate.votingproxy.delete()
            return delegate

        # Add voter id to proxies list.
        proxies.append(delegate.id)
        delegate = representation

    return delegate


def get_admitted_delegates(principle, *order_by):
    """
    Returns a list of admitted delegates and the count of all possible votes.
    Admitted delegates are users in the delegate group that do not have a proxy
    AND are present. The votes count also counts proxies. If A is a proxy of B and
    A is present, the list contains only A, but the count would be 2.

    :param principle: Principle or None.
    :param order_by: User fields the list should be ordered by.
    :return: (list, int)
    """
    # Get delegates who have voting rights (shares) for the given principle.
    admitted = query_admitted_delegates(principle=principle)
    if order_by:
        admitted = admitted.order_by(*order_by)

    admitted_list = []
    votes_count = 0
    for delegate in admitted.select_related('votingproxy').all():
        auth_voter = find_authorized_voter(delegate)
        if auth_voter is not None and auth_voter.is_present:
            votes_count += 1
            if auth_voter not in admitted_list:
                admitted_list.append(auth_voter)
    return (votes_count, admitted_list)


def get_admitted_delegates_with_keypads(principle, *order_by):
    """
    Returns a list of admitted delegates and the votes_count similar
    to get_admitted_delegates(). Admitted delegates are users in the
    delegate group AND are present AND have a keypad assigned.

    :param principle: Principle or None.
    :param order_by: User fields the list should be ordered by.
    :return: (int, list): expected votes count and admitted_delegates with keypads
    """
    # Get delegates who have voting rights (shares) for the given principle.
    admitted = query_admitted_delegates(principle=principle)
    if order_by:
        admitted = admitted.order_by(*order_by)

    admitted_list = []
    votes_count = 0
    for delegate in admitted.select_related('votingproxy').all():
        auth_voter = find_authorized_voter(delegate)
        if auth_voter is not None and auth_voter.is_present and hasattr(auth_voter, 'keypad'):
            votes_count += 1
            if auth_voter not in admitted_list:
                admitted_list.append(auth_voter)
    return (votes_count, admitted_list)


def query_admitted_delegates(principle=None):
    """
    Returns a queryset of admitted delegates.

    Admitted delegates are users belonging to the Delegates group (default id is
    2), AND who have ANY voting rights (shares) if voting shares exist, AND who
    have voting rights for a given voting principle (principle_id).

    :param principle: Principle or None.
    :return: queryset
    """
    delegate_group_id = getattr(settings, 'DELEGATE_GROUP_ID', 2);
    qs = User.objects.filter(groups=delegate_group_id)
    if VotingShare.objects.exists():
        qs = qs.filter(shares__shares__gt=0).distinct()  # distinct is required to eliminate duplicates
    if principle:
        qs = qs.filter(shares__principle=principle)
    return qs


class BaseBallot:
    """
    The interface to care about the actual modification of different ballot types
    for a given poll.
    """

    def __init__(self, poll):
        """
        Creates a Ballot instance for a given poll object.
        """
        self.poll = poll

    def delete_ballots(self):
        """
        Deletes all ballot objects of the current poll. Returns the number of ballots deleted.
        """
        raise NotImplementedError('This function needs to be implemented')

    def create_absentee_ballots(self, principle=None):
        """
        Creates ballot objects for all voting delegates who have cast an absentee vote.
        Objects are created even if the delegate is present or whether or not a proxy
        is present. Returns the number of absentee ballots.
        """
        raise NotImplementedError('This function needs to be implemented')

    def get_next_result_token(self):
        """
        Returns the next result token for this poll.
        """
        raise NotImplementedError('This function needs to be implemented')

    def register_vote(self, vote, voter=None, principle=None, result_token=0):
        """
        Register a vote by creating ballot objects for the voter and all proxies represented
        by the voter. The shares will not be checked here. Fot the voter and every proxy the
        vote will be registered. During count_votes, the shares will be included. If voter
        is none, just the vote is registered, because we do not know the proxy chain.
        The return value is the count of created or update ballots **respecting the principle**.
        If some of the users doesn't have a share, they are not counted!

        Ballot objects will not be created for any delegate who submitted an absentee vote. For
        this see the create_absentee_ballots function.

        vote: Vote, typically 'Y', 'N', 'A' or an ID
        voter: User, may be None
        Returns th number of ballots created (and NOT updated).
        """
        created = 0
        if voter is None:
            if self._create_ballot(vote, result_token=result_token):
                created += 1
        else:
            principle_id = principle.id if principle is not None else None
            # Register the vote and proxy votes.
            delegates_to_create_ballot = [voter]
            while len(delegates_to_create_ballot) > 0:
                delegate = delegates_to_create_ballot.pop()
                delegates_to_create_ballot.extend([proxy.delegate for proxy in delegate.mandates.all()])
                if self._create_ballot(vote, delegate=delegate, result_token=result_token):
                    # Just count the ballot, if the user has voting shares
                    if principle_id is not None:
                        shares = delegate.shares.filter(principle__pk=principle_id)
                        if shares.count() != 0 and shares.first().shares > 0:
                            created += 1
                    else:
                        created += 1

        return created


    def count_votes(self):
        """
        Counts the votes of all ballot objects for the given poll. The returned format
        depends heavily of the actual ballot and poll. Look in the docstrings of the child
        classes to get mor information. These results always have to be handled separately!
        """
        raise NotImplementedError('This function needs to be implemented')

    def pseudoanonymize_votes(self):
        """
        Delete all user references for all ballots for this poll.
        """
        raise NotImplementedError('This function needs to be implemented')

    def _create_ballot(self, vote, delegate=None, result_token=0):
        """
        Helper function to actually create or update a ballot.
        Returns True, if a ballot was created.
        """
        raise NotImplementedError('This function needs to be implemented')


class MotionBallot(BaseBallot):
    """
    Creates, deletes, updates MotionPollBallot objects for a given MotionPoll object.
    For more docstring read the descriptions in BaseBallot.
    """

    def delete_ballots(self):
        """
        Deletes all MotionPollBallot objects of the current poll.
        """
        deleted = []
        collection_string = MotionPollBallot.get_collection_string()
        for pk in MotionPollBallot.objects.filter(poll=self.poll).values_list('pk', flat=True):
            deleted.append((collection_string, pk))
        deleted_count, _ = MotionPollBallot.objects.filter(poll=self.poll).delete()
        inform_deleted_data(deleted)
        return deleted_count

    def create_absentee_ballots(self, principle=None):
        """
        Creates or updates all motion poll ballots for every admitted delegate that has an
        absentee vote registered. Returns the amount of absentee votes.
        """
        # Allow only absentee votes of admitted delegates.
        admitted_delegates = query_admitted_delegates(principle=principle)

        # Query absentee votes for given motion.
        absentee_votes = MotionAbsenteeVote.objects.filter(motion=self.poll.motion).filter(delegate__in=admitted_delegates)

        ballots_to_create = []
        delegate_ids = []
        for absentee_vote in absentee_votes.all():
            # Update or create ballot instance.
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=absentee_vote.delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=absentee_vote.delegate, result_token=0)
            mpb.vote = absentee_vote.vote
            if mpb.pk:
                mpb.save(skip_autoupdate=True)
            else:
                ballots_to_create.append(mpb)
            delegate_ids.append(mpb.delegate.id)

        # Bulk create ballots.
        MotionPollBallot.objects.bulk_create(ballots_to_create)

        # Trigger auto-update.
        created_ballots = MotionPollBallot.objects.filter(poll=self.poll, delegate_id__in=delegate_ids)
        inform_changed_data(created_ballots)

        return len(delegate_ids)

    def get_next_result_token(self):
        """
        Returns the next result token for this poll.
        """
        used_tokens = MotionPollBallot.objects.filter(poll=self.poll).values_list('result_token', flat=True)
        return MotionPollBallot.get_next_result_token(used_tokens)

    def count_votes(self):
        """
        Counts the votes of all MotionPollBallot objects for the given poll. The result
        is a dict with values for yes, no and abstain, casted, valid and invalid. In this
        case the values for casted and valid are equal, the values for invalid are zero.
        Each entry in the result dict is a list with two enties: First the heads and second
        the shares (heady with weights). If a head does not have a share, it will be weighted
        by 1.
        Just the ballot are counted, that does not have a user or the user must have shares >0.

        Returns the result dict. For the structure look for the `result = {` definition below.
        """
        # Convert the ballots into a list of (delegate_id, vote) tuples.
        # Example: [(1, 'Y'), (2, 'N')]
        votes = MotionPollBallot.objects.filter(poll=self.poll).values_list('delegate', 'vote')

        shares = None
        # try to find a voting principle
        principle = VotingPrinciple.objects.filter(motions=self.poll.motion).first()
        if principle is not None:
            # Create a dict (key: delegate, value: shares).
            # Example: {1: Decimal('1.000000'), 2: Decimal('45.120000')}
            voting_shares = VotingShare.objects.filter(principle=principle)
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
            if delegate_id is None:
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

    def pseudoanonymize_votes(self):
        """
        Delete all user references for all ballots for this poll.
        """
        ballots = MotionPollBallot.objects.filter(poll=self.poll)
        for mpb in ballots:
            mpb.delegate = None
            mpb.save()

    def _create_ballot(self, vote, delegate=None, result_token=0):
        """
        Helper function to actually create or update a ballot.
        """
        created = False
        if delegate is not None:
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=delegate)
                created = True
        else:
            mpb = MotionPollBallot(poll=self.poll)
            created = True

        mpb.vote = vote
        mpb.result_token = result_token
        mpb.save()
        return created


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

    def _create_ballot(self, vote, delegate=None, result_token=0):
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

        apb.vote = vote
        apb.result_token = result_token
        apb.save()
        return created
