from openslides.users.models import User
from openslides.utils.autoupdate import inform_changed_data, inform_deleted_data

from .models import AbsenteeVote, MotionPollBallot, VotingShare, VotingPrinciple, Keypad


def find_authorized_voter(delegate, proxies=None):
    """
    Find the authorized voter of a delegate by recursively stepping through the proxy chain.

    :param delegate: User object
    :param proxies: List of proxy IDs found so far, used to eliminate circular references
    :return: authorized user (the last one in the proxy chain)
    """
    # NOTE: Function might be slow with many db hits.
    if hasattr(delegate, 'votingproxy'):
        rep = delegate.votingproxy.proxy
        if proxies is None:
            proxies = []
        elif rep.id in proxies:
            # We have a circular reference. Delete the voting proxy to fix it.
            # TODO: Log circular ref error and/or notify user.
            delegate.votingproxy.delete()
            return delegate

        # Add voter id to proxies list.
        proxies.append(delegate.id)

        # Recursively step through the proxy chain.
        return find_authorized_voter(rep, proxies)

    return delegate


def get_admitted_delegates(principle_id, *order_by):
    """
    Returns a dictionary of admitted delegates.

    :param principle_id: Principle ID or None.
    :param order_by: User fields the list should be ordered by.
    :return: Dictionary, count
    """
    # Get delegates who have voting rights (shares) for the given principle.
    # admitted: key: keypad number, value: list of delegate ids
    admitted = {}
    qs_delegates = query_admitted_delegates(Principle.objects.get(pk=principle_id))
    if order_by:
        qs_delegates = qs_delegates.order_by(*order_by)

    # Only admit those delegates whose authorized voter is registered,
    # i.e. present with keypad assigned.
    count = 0
    for delegate in qs_delegates.select_related('votingproxy', 'keypad'):
        auth_voter = find_authorized_voter(delegate)
        if is_registered(auth_voter):
            key = auth_voter.keypad.number
            if key in admitted:
                admitted[key].append(delegate.id)
            else:
                admitted[key] = [delegate.id]
            count += 1

    return admitted, count


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
    if printciple:
        qs = qs.filter(shares__principle=principle)
    return qs


def is_registered(delegate):
    """
    Returns True if delegate is present and a keypad has been assigned.
    :param delegate: User object
    :return: bool
    """
    return delegate is not None and hasattr(delegate, 'keypad') and delegate.is_present


class Ballot:
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
        self.admitted_delegates = None
        self.new_ballots = None
        self._clear_result()

    def delete_ballots(self):
        """
        Deletes all MotionPollBallot objects of the current poll.

        :return: Number of ballots deleted.
        """
        args = []
        for pk in MotionPollBallot.objects.filter(poll=self.poll).values_list('pk', flat=True):
            args.append(MotionPollBallot.get_collection_string())
            args.append(pk)
        deleted_count, _ = MotionPollBallot.objects.filter(poll=self.poll).delete()
        if args:
            inform_deleted_data(*args)
        self._clear_result()
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
            VotingPrinciple.objects.get(motion=self.poll.motion))
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

    def register_vote(self, keypad, vote, commit=True):
        """
        Register a vote and all proxy votes by creating MotionPollBallot objects for the voter and any delegate
        represented by the voter.

        A vote is registered whether or not a proxy exists! The rule is not to assign a keypad to a
        delegate represented by a proxy but we don't enforce this rule here.

        MotionPollBallot objects will not be created for any delegate who submitted an absentee vote.

        :param keypad: Keypad ID
        :param vote: Vote, typically 'Y', 'N', 'A'
        :param commit: if True saves new MotionPollBallot instances else caches them in self.new_ballots
        :return: Number of ballots created or updated.
        """
        self.updated = 0
        # Get delegate user the keypad is assigned to.
        try:
            voter = User.objects.get(keypad__number=keypad)
        except User.DoesNotExist:
            return self.updated

        # Create a list of admitted delegate ids. Exclude delegates who cast an absentee vote.
        qs = query_admitted_delegates(
            VotingPrinciple.objects.get(motion=self.poll.motion)
            ).exclude(absenteevote__motion=self.poll.motion)
        self.admitted_delegates = qs.values_list('id', flat=True)

        if not commit and self.new_ballots is None:
            self.new_ballots = []

        # Register the vote and proxy votes.
        self._register_vote_and_proxy_votes(voter, vote)
        return self.updated

    def save_ballots(self):
        """
        Bulk saves cached motion poll ballots.
        :return: Total number of motion poll ballots
        """
        if self.new_ballots:
            # Bulk create ballots.
            MotionPollBallot.objects.bulk_create(self.new_ballots)

            # Trigger auto-update.
            delegate_ids = [b.delegate.id for b in self.new_ballots]
            created_ballots = MotionPollBallot.objects.filter(poll=self.poll, delegate_id__in=delegate_ids)
            inform_changed_data(created_ballots)

            self.new_ballots = None

        return MotionPollBallot.objects.filter(poll=self.poll).count()

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
        self._clear_result()
        for vote in votes:
            k = vote[1]
            try:
                sh = shares[vote[0]] if shares else 1
            except KeyError:
                # Occurs if voting share was removed after delegate cast a vote.
                pass
            else:
                self.result[k][0] += 1
                self.result[k][1] += sh
                self.result['casted'][0] += 1
                self.result['casted'][1] += sh
        self.result['valid'] = self.result['casted']

        # TODO NEXT: Add 'not voted abstains' option.
        return self.result

    def _register_vote_and_proxy_votes(self, voter, vote):
        self._create_ballot(voter, vote)
        for proxy in voter.mandates.all():
            self._register_vote_and_proxy_votes(proxy.delegate, vote)

    def _create_ballot(self, delegate, vote):
        if delegate.id in self.admitted_delegates:
            try:
                mpb = MotionPollBallot.objects.get(poll=self.poll, delegate=delegate)
            except MotionPollBallot.DoesNotExist:
                mpb = MotionPollBallot(poll=self.poll, delegate=delegate)
            mpb.vote = vote
            if mpb.pk or self.new_ballots is None:
                mpb.save()
            else:
                self.new_ballots.append(mpb)
            self.updated += 1

    def _clear_result(self):
        from decimal import Decimal
        self.result = {
            'Y': [0, Decimal(0)],  # [heads, shares]
            'N': [0, Decimal(0)],
            'A': [0, Decimal(0)],
            'casted': [0, Decimal(0)],
            'valid': [0, Decimal(0)],
            'invalid': [0, Decimal(0)]
        }
