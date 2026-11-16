# Test fixtures

Real answers captured by the CTO on 2026-11-16. Fakes answer with these files so tests see the same fields the real devices send.

- `tv/`: the TV's SmartCast API (`192.168.1.130`), read-only calls. Each file is `{"http_status": <int>, "body": <the JSON answer>}`.
- `plex/`: the Plex Media Server (`/identity`, `/library/sections`, `/hubs/continueWatching`, `/hubs?count=3`, `/hubs/sections/1` and `/2`, `POST /playQueues`, `/library/metadata/<id>` for an episode, a movie and a show, a show's `allLeaves`, and one GDM reply). Each `.json` file is the answer body as sent. Lists are cut to 2-3 entries. Every title, name, summary, file path, timestamp and server identifier was replaced by a placeholder such as `"title 12"`; the structure, field names and value types are the server's.

Only the CTO recaptures these, with a scrubbing script kept outside the repository. Never add real titles or identifiers here: the repository is public.
