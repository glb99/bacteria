HQ — Case study — Cloudstudio
cloudstudio*
← Work
Case study
Case study · Cloudstudio internal
HQ
Every project in production, every repository and every Stripe account, as
a colony on Mars
you can walk around. When something falls over, you see it from the other side of the valley.
Read the log
All work
Sol 46 · flyover
41 modules · 9 warnings · 2 down
Client
Cloudstudio — internal
Deliverable
Real-time infrastructure monitor
Role
Concept, design & engineering
Year
2026 · Valencia
( The brief )
Nobody reads
a dashboard.
Ten sites in production, fourteen public repositories, a Stripe account, certificates expiring on their own schedule. All of it visible, in theory, across five browser tabs nobody opened until something broke.
The problem was never the data — it was that a table of green ticks carries no weight. You skim it. So HQ throws the table away and gives the estate a
place
: a valley on Mars where every single thing you own stands up as a building, at the size its numbers earn. You don't check on it. You look out of the window.
If there's no data behind a building, the
building doesn't exist
.
Sol 001
One built volume, one real thing.
The rule that makes the whole thing work, and the one that was hardest to keep. No building is ever invented to fill a gap. A habitat dome is a project answering HTTP right now; a greenhouse is a repository; an ice extractor is a Stripe account. Few things means a small colony — and it grows on its own as you ship, without anyone laying out a map. The only volumes with nothing behind them are landscape, and the world says so out loud: matte rust, never data.
Production, Clients, Labs, Infrastructure — one sector per area, laid out from the data
Sol 007
Colour before text.
A state has to land before you read a word of it. Cyan holds steady when a thing answers. Magenta pulses when something wants attention — a certificate with nineteen days left, four pull requests waiting. A downed service strobes white and its hull goes dark, and it never dims to nothing, because a module that blinks to black disappears at exactly the moment you need it most.
Alive
Answers, and there's nothing pending.
Warning
Certificate about to expire, issues open, work uncommitted.
Down
Refused the connection, or the domain no longer resolves.
Matte rust
Landscape. It never states a fact.
Sol 014
A vocabulary, written down before it was built.
Twenty-seven pieces, each with what it would actually be for on Mars and what it stands for here. Writing that list first is what stopped the world drifting into decoration: three pieces are still not placed, and they're documented as unplaced, because the data behind them doesn't exist. A refinery that "turns HTTP responses into state" is a lovely metaphor and a fact nobody can measure.
The inventory — the vocabulary, and the audit trail for it
Sol 023
The work that hasn't shipped.
An open-pit quarry, out past the last plot, where the crew cuts the raw material the colony is built from: the commits still sitting on the machine. Three benches, a haul road with kerbs, a braced drill rig whose bit turns and sinks. The crew has jobs, not one animation — two cut the face, one shovels, one pushes a cart up the road and stops at each end to load and tip. Dust comes off on the frame the pick lands, not before.
Local commits, cut by hand
Sol 031
Where the agents come back to.
A pressurised hangar on the civic avenue, and the only building that reports on the work itself rather than on a thing you own: who is out on the surface and what they're doing. When there's nothing wired in, it says so — the panel reads "pending: the MCP that wires the agents in" instead of pretending. A world that lies once about being busy stops being worth looking at.
The hangar reports the queue, or reports that there isn't one
Sol 038
Something to measure the rest against.
A cargo ship stands out past the base on its own sintered pad, thirty-three metres of it — six legs in tripods, engine bells under the skirt, scorch thrown radially across the ground. It's the one thing in the valley that carries no data at all, and it earns its place by doing the job nothing else can: giving everything else a size. Without it a habitat dome is an abstract shape. Next to it, it's a building you could walk into.
Landscape, and the reason the rest reads as architecture
Sol 046
Money that arrives while you're watching.
A charge lands and the ice extractor it belongs to puts up a tag with the amount. Click it and the colony throws a small party — a burst of colour over the module — and the charge is marked collected and never asks again. A refund is not a sale, so it never becomes a pin: it goes into the ledger, where accounting belongs, and stays out of the sky, where alarms belong.
Treasury — one extractor per account
( Under the hood )
Rhythms, measured
Production every 60 s, local repos every 5 min, GitHub every 15, Stripe every hour, certificates every twelve. Those numbers were measured, not guessed: the limit that actually binds on Stripe isn't the hundred requests a second, it's the monthly read allowance. Polling every five minutes burned
432 %
of it.
Geometry that stays cheap
Every building is baked down to vertex colours and merged by material, keeping only the parts that have to move or change state. A hundred modules land in comfortable territory — and the mining crew, the rover and the drones animate on top without the frame budget noticing.
Nothing leaves the machine
No key lives in the repository. GitHub goes through the
gh
session you already have, Stripe through the CLI's keychain, production through real HTTP requests to your own domains. The snapshot is gitignored on purpose: it holds local paths, identities and revenue.
Look out of the window.
We design and build products where the interface carries the idea — 3D, motion, and the boring parts underneath. Tell us what you want to launch.
Book a call
github.com/cloudstudio ↗
Next case study
Agents
→
cloudstudio.es
·
Est. 2008 · Valencia
·
hello@cloudstudio.es