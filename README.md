# S7bb Factsheet

S7bb is a small, independent project that tracks the **operational quality of
the S-Bahn line S7 at the station Baierbrunn** (Munich S-Bahn network):
availability, punctuality, whether trains actually reach their destination, and
how cancellations affect the picture.

It is a community effort built from publicly observable arrival data. Nothing
here is official.

📄 **[Latest factsheet (PDF)](https://github.com/s7bb/factsheet/releases/latest)** —
the most recent monthly one-pager, always pointing at the newest release.

## Repositories

| Repository | Purpose |
| --- | --- |
| [**s7bb/s7bb**](https://github.com/s7bb/s7bb) | The S7bb **web application** — an interactive view of the S7/Baierbrunn data, intended to be **run locally** for your own use. Start here if you want to explore the data interactively. |
| [**s7bb/s7bb-data**](https://github.com/s7bb/s7bb-data) | The **data repository**. Raw, archived arrival records per month as `archive/<YYYY-MM>.json`. This is the single source of truth that the other repositories read from. |
| [**s7bb/factsheet**](https://github.com/s7bb/factsheet) | *(this repo)* Generates a one-page **PDF factsheet** (German, DIN A4) summarising a month of S7/Baierbrunn operation. Runs monthly and publishes each PDF as a GitHub Release tagged `MM.YYYY`. See [`factsheet/README.md`](factsheet/README.md). |

## Data

All numbers ultimately come from [s7bb/s7bb-data](https://github.com/s7bb/s7bb-data).
It holds one finalized JSON file per month; the factsheet and the web
application both read from it, so the figures they show are consistent.

## Disclaimer

**S7bb is an independent, non-commercial project. It is not affiliated with,
endorsed by, or connected to Deutsche Bahn AG, DB Regio, S-Bahn München, or the
Münchner Verkehrs- und Tarifverbund (MVV).**

"S-Bahn", "Deutsche Bahn", "DB", and related names and logos are trademarks of
their respective owners and are used here only to describe the service being
observed. The data is collected from publicly observable arrival information and
may be incomplete or contain errors. It is provided **as is, without warranty of
any kind**, for informational purposes only, and is not an official statement of
service quality. For official information, refer to Deutsche Bahn / S-Bahn
München directly.

## Colophon

The code in this repository was created with
[Claude Code](https://claude.com/claude-code) and the Superpowers skill set.
