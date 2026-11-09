# Security policy

This project is a beta. The supported deployment is a private LAN/Tailnet or an
HTTPS reverse proxy configured with a fixed external origin. Do not enable public
Funnel access or direct internet port forwarding for this beta.

Do not post session files, signed download URLs, cookies, appdata backups,
passwords, or unredacted logs in public issues. Until a public repository and a
private reporting channel exist, report suspected issues privately to the project
owner through the existing private communication channel. A public reporting URL
must be configured before distribution; no response-time SLA is promised yet.

When a repository is created, enable GitHub private vulnerability reporting and
replace this paragraph with its verified reporting URL. Reproduce issues using
synthetic fixtures wherever possible.

Security fixes are developed on the current beta line. Older snapshots have no
ongoing support promise. Release candidates require dependency and image scanning,
SBOMs, and a reviewed security report; passing a scan is not a security guarantee.
