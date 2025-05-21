Release type: minor

In this release, the non-standard `extensions` field was removed from the `data` message payload in the legacy GraphQL over WS protocol.
This field was accidentally added, undocumented, and untested.
