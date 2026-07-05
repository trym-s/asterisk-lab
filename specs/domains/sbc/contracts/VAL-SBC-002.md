# VAL-SBC-002: Asterisk-originated B2BUA leg does not loop

Surface: SIP call flow.
Needs: Passing `VAL-SBC-001` and two endpoints registered through the SBC, or an
equivalent controlled B2BUA call setup.
Behavior: When Asterisk creates an outbound `Dial(PJSIP/<ext>)` leg, the SBC
does not set `$du` back to Asterisk for that initial INVITE; the request follows
the R-URI toward the registered softphone.
Evidence: Validator records the relevant OpenSIPS config rendering and a
sngrep trace for a direct `_10XX` call showing the outbound leg leaves the SBC
toward the softphone instead of returning to Asterisk.
Fail: Repeated INVITE loop to Asterisk or a source-independent `$du` assignment
in the initial INVITE branch means failure.
