# openslides-voting
Voting plugin for OpenSlides

## Settings

`VOTING_RESULT_TOKEN_TIMEOUT`: The timeout in seconds until vote success view is
closed dureng token voting. This is important, so the next one cannot get the
result token, if the user didn't click on continue. This can be disabled, when
setting the timeout to 0.
