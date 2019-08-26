# CHANGELOG of OpenSlides Voting Plugin

## Version 3.1 (2019-08-26)
* new prompts for Interact Mini device
* new config option: Sort delegates by keypad nummer on delegate board
* new config option: hide name or keypad number on delegate board
* new config option: No vote counted as abstention
* Update attendance every 10 seconds
* Show key of voting device for each seat on delegate board (for elections)
* Restrict absentee votes
* Only create absentee votes if authorized voter present with keypad.
* Projector performance boost if no delegate board shown.
* Fixed access permission to read voting principles for normal users.
* Bug fix: Abstaining vote was rejected
* updated translations

## Version 3.0.1 (2018-09-28)
* Used new VoteCollector 1.10.1 which checks if secret key is available on start voting.
* Fixed sorting in poll type form.
* Added missing translations.

## Version 3.0 (2018-09-20)
* rewrite of old OpenSlides VoteCollector Plugin
  with VoteCollector votings modes
* new voting modes
  - Named electronic voting
  - Token-based electronic voting
* voting shares
* proxies/principals and abstentee votes
* new delegate board


For older releases of outdated OpenSlides VoteCollector Plugin see
https://github.com/OpenSlides/openslides-votecollector#changelog
