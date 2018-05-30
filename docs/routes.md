#API routes
All API route definitions are done in `openslides_voting/views.py`. They are
handled by the REST-API. The prefix for all voting related stuff is
`/rest/openslides_voting/voting-controller/1/`.

- `start_motion` and `start_assignment`. Both routes starts a poll and need to
  get the poll id as the only argument: `{poll_id: <poll-id>}`.

  Things the server does then:
  - get the voting type and principle
  - if the type is 'votecollector', messages for the projector are expanded with
    instructions for the keypads
  - absentee ballots are created
  - if the type is 'votecollector', the votecollector is started.
  - All admitted delegates are queried (with respect for the voting type)
  - The votingcontroller and authorizedVoters model are updated
  - The projector message gets projected and (if enabled) a countdown is started

  The response is 200 OK and empty on success.

- `results_motion_votes` and `results_assignment_votes`. Both routes returns the
  results of a given poll by `{poll_id: <poll-id>}`. Note that this poll has to
  be active.

  All responses are JSON with the following structures. Motions:
  ```
  result = {
      'Y': [0, Decimal(0)],  # [heads, shares]
      'N': [0, Decimal(0)],
      'A': [0, Decimal(0)],
      'casted': [0, Decimal(0)],
      'valid': [0, Decimal(0)],
      'invalid': [0, Decimal(0)]
  }
  ```
  Assignments with YN(A) pollmethod:
  ```
  result = {
      <candidate_id_1>: {
          'Y': [<heads>, <shares>],
          'N': [<heads>, <shares>],
          ('A': [<heads>, <shares>],)
      },
      ...
      'casted': [<heads>, <shares>],
      'valid': [<heads>, <shares>],
      'invalid': [<heads>, <shares>],
  }
  ```
  Assignments with votes pollmethod:
  ```
  result = {
      <candidate_id_1>: [<heads>, <shares>],
      ...
      'casted': [<heads>, <shares>],
      'valid': [<heads>, <shares>],
      'invalid': [<heads>, <shares>],
  }
  ```

- `clear_motion_votes` and `clear_assignment_votes`. Both routed needs the poll
  id from an active poll given by `{poll_id: <poll-id>}`. All
  MotionPoll/AssignmentPoll objects for this poll are deleted and all
  MotionPollBallots/AssignmentPollBallots, too. An empty response is returned.

- `stop`: The current voting gets stopped. Also the countdown is stopped and the
  projector hint is removed. The votecollector is stopped, if enabled. The
  authorized voter model is cleared.

The VotingToken Model allows to generate random tokens. Send a request to
`/rest/openslides_voting/voting-token/generage/` with `{N: <n>}` (1<=N<=4096) as
argument. The response is an array of random tokens with the length 12.

# Voting recieve routes
The routes are defined in `openslides_voting/votecollector/urls.py`.

- `/votingcontroller/(votecollector/)vote/<poll-id>/`. Here should be YN(A)
  votes for motions and elections be submitted. If the votecollector is used,
  they have to go to the votecollector-url, if another voting mode is used, the
  votecollector part has to be omitted. The poll id has to be the current voting
  target.
  For the input data format see docstrings in
  `openslides_voting/votecollector/views.py`. For named and token based
  eelctronic voting, the client can send just one vote dict or an array with one
  vote dict, but not more. The votecollector has to send an array of (maybe)
  multiple dicts.

- `/votingcontroller/(votecollector/)candidate/<poll-id>/`. Here all candidate
  votes for an election should be submitted. Every thing is the same as for
  `/votes/`.
