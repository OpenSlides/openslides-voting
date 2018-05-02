from decimal import Decimal

from openslides.users.models import User
from openslides.utils.autoupdate import inform_changed_data, inform_deleted_data

from .models import AbsenteeVote, MotionPollBallot, VotingShare, VotingPrinciple, Keypad


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
    Returns a list of admitted delegates.
    Admitted delegates are users in the delegate group AND
    are present

    :param principle: Principle or None.
    :param order_by: User fields the list should be ordered by.
    :return: list
    """
    # Get delegates who have voting rights (shares) for the given principle.
    # admitted: key: keypad number, value: list of delegate ids
    admitted = query_admitted_delegates(principle)
    if order_by:
        admitted = admitted.order_by(*order_by)

    admitted_list = []
    for delegate in admitted.select_related('votingproxy').all():
        auth_voter = find_authorized_voter(delegate)
        if auth_voter is not None and auth_voter.is_present and auth_voter not in admitted_list:
            admitted_list.append(auth_voter)
    return admitted_list


def get_admitted_delegates_with_keypads(principle, *order_by):
    """
    Returns a dict of keypad numbers to list of admitted delegate ids.
    Admitted delegates are users in the delegate group AND
    are present AND have a keypad assigned

    :param principle: Principle or None.
    :param order_by: User fields the list should be ordered by.
    :return: list of delegates
    """
    admitted = [delegate for delegate in get_admitted_delegated(principle, *order_by) if hasattr(delegate, 'kaypad')]
    return admitted

    """
    admitted_dict = {}
    count = 0
    for delegate in admitted:
        if hasattr(delegate, 'keypad'):
            key = delegate.keypad.number
            if key in admitted_dict:
                admitted_dict[key].append(delegate.id)
            else:
                admitted_dict[key] = [delegate.id]
            count += 1

    return admitted_dict, count
    """


def query_admitted_delegates(principle=None):
    """
    Returns a queryset of admitted delegates.

    Admitted delegates are users belonging to the Delegates group (id = 2), AND
    who have ANY voting rights (shares) if voting shares exist, AND
    who have voting rights for a given voting principle (principle_id).

    :param principle: Principle or None.
    :return: queryset
    """
    qs = User.objects.filter(groups=2)
    if VotingShare.objects.exists():
        qs = qs.filter(shares__shares__gt=0).distinct()  # distinct is required to eliminate duplicates
    if principle:
        qs = qs.filter(shares__principle=principle)
    return qs


class MotionBallot:
    """
    Creates, deletes, updates MotionPollBallot objects for a given MotionPoll object.
    Registers votes including proxy votes.
    """

    def __init__(self, poll):
        """
        Creates a Ballot instance for a given MotionPoll object.
        :param poll: MotionPoll
        """
        self.poll = poll

    def delete_ballots(self):
        """
        Deletes all MotionPollBallot objects of the current poll.

        :return: Number of ballots deleted.
        """
        args = []
        for pk in MotionPollBallot.objects.filter(poll=self.poll).values_list('pk', flat=True):
            args.append((MotionPollBallot.get_collection_string(), pk))
        deleted_count, _ = MotionPollBallot.objects.filter(poll=self.poll).delete()
        if len(args):
            inform_deleted_data(args)
        return deleted_count

    def create_absentee_ballots(self):
        """
        Creates MotionPollBallot objects for all voting delegates who have cast an absentee vote.
        Objects are created even if the delegate is present or whether or not a proxy is present.

        :return: Number of ballots created or updated.
        """
        # Query absentee votes for given motion.
        qs_absentee_votes = AbsenteeVote.objects.filter(motion=self.poll.motion)

        # Allow only absentee votes of admitted delegates.
        admitted_delegates = query_admitted_delegates(
            VotingPrinciple.objects.get(motions=self.poll.motion))
        qs_absentee_votes = qs_absentee_votes.filter(delegate__in=admitted_delegates)

        updated = 0
        ballots = []
        delegate_ids = []
        for absentee_vote in qs_absentee_votes:
            # Update or create ballot instance.
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=absentee_vote.delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=absentee_vote.delegate)
            mpb.vote = absentee_vote.vote
            if mpb.pk:
                mpb.save(skip_autoupdate=True)
            else:
                ballots.append(mpb)
            delegate_ids.append(mpb.delegate.id)
            updated += 1

        # Bulk create ballots.
        MotionPollBallot.objects.bulk_create(ballots)

        # Trigger auto-update.
        created_ballots = MotionPollBallot.objects.filter(poll=self.poll, delegate_id__in=delegate_ids)
        inform_changed_data(created_ballots)

        return updated

    def register_vote(self, vote, voter=None):
        """
        Register a vote and all proxy votes by creating MotionPollBallot objects for the voter
        and any delegate represented by the voter.

        A vote is registered whether or not a proxy exists! The rule is not to assign a keypad
        to a delegate represented by a proxy but we don't enforce this rule here.

        MotionPollBallot objects will not be created for any delegate who submitted an absentee vote.

        :param vote: Vote, typically 'Y', 'N', 'A'
        :param voter: User
        :return: Number of ballots created or updated.
        """
        created = 0
        if voter is None:
            self._create_ballot(vote)
            created = 1
        else:
            # Register the vote and proxy votes.
            delegates_to_create_ballot = [voter]
            while len(delegates_to_create_ballot) > 0:
                delegate = delegates_to_create_ballot.pop()
                delegates_to_create_ballot.extend([proxy.delegate for proxy in delegate.mandates.all()])
                self._create_ballot(vote, delegate)
                created += 1

        return created

    def count_votes(self):
        """
        Counts the votes of all MotionPollBallot objects for the given poll and saves the result
        in a RESULT dictionary.
        :return: Result
        """
        # Convert the ballots into a list of (delegate, vote) tuples.
        # Example: [(1, 'Y'), (2, 'N')]
        qs = MotionPollBallot.objects.filter(poll=self.poll)
        votes = qs.values_list('delegate', 'vote')

        shares = None
        # try to find a voting principle
        principle = VotingPrinciple.objects.filter(motions=self.poll.motion)
        if principle.count() > 0:
            # Create a dict (key: delegate, value: shares).
            # Example: {1: Decimal('1.000000'), 2: Decimal('45.120000')}
            qs = VotingShare.objects.filter(principle_id=principle.all()[0])
            shares = dict(qs.values_list('delegate', 'shares'))

        # Sum up the votes.
        result = {
            'Y': [0, Decimal(0)],  # [heads, shares]
            'N': [0, Decimal(0)],
            'A': [0, Decimal(0)],
            'casted': [0, Decimal(0)],
            'valid': [0, Decimal(0)],
            'invalid': [0, Decimal(0)]
        }
        for vote in votes:
            k = vote[1]
            try:
                sh = shares[vote[0]] if shares else 1
            except KeyError:
                # Occurs if voting share was removed after delegate cast a vote.
                pass
            else:
                result[k][0] += 1
                result[k][1] += sh
                result['casted'][0] += 1
                result['casted'][1] += sh
        result['valid'] = result['casted']

        # TODO NEXT: Add 'not voted abstains' option.
        return result

    def _create_ballot(self, vote, delegate=None):
        if delegate is not None:
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=delegate)
        else:
            mpb = MotionPollBallot(poll=self.poll)

        mpb.vote = vote
        mpb.save()
