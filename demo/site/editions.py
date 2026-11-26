"""The demo story, edition by edition. Everything here is fictional: the town, the project, the
council and the numbers. Each edition changes specific sections, so a refresh shows the engine
redoing only the segments whose sources changed (FR8).

- Edition 1: the story as first published.
- Edition 2: the timeline slips (only "Timeline" changes).
- Edition 3: sign-ups open (a new "Subscriptions open" section; "Timeline" as in edition 2).
"""

TITLE = "Port Arden's community solar farm: what we know"

OVERVIEW = (
    "Overview",
    [
        "Port Arden's town council has approved a four-megawatt community solar farm on the old "
        "rail yard north of the harbour. Councillors voted six to one in favour on the 28th of "
        "October. The farm is expected to supply about nine hundred homes, roughly a fifth of "
        "the town.",
        "It will be the first community-owned power project in the region. The town will own the "
        "land and the panels, and a non-profit co-operative will run the farm day to day.",
    ],
)

SUBSCRIPTION = (
    "How the subscription works",
    [
        "Residents do not need panels on their own roof. Instead, they subscribe to a share of "
        "the farm's output and receive a credit on their electricity bill for the power that "
        "share produces.",
        "The smallest share is one kilowatt, which costs about eight dollars a month. The "
        "co-operative expects that share to earn a bill credit of about ten dollars a month. "
        "Renters can subscribe too, and a share moves with the subscriber if they move within "
        "town.",
    ],
)

FUNDING = (
    "Cost and funding",
    [
        "The project is budgeted at seven point two million dollars. A provincial clean energy "
        "grant covers three million of that, and a green bond issued by the town covers two and "
        "a half million.",
        "The remaining one point seven million will come from subscriber fees over the first five "
        "years. The council says no money will come from property taxes.",
    ],
)

TIMELINE_1 = (
    "Timeline",
    [
        "Site preparation is planned to start in January 2027. The panels are due to be installed "
        "over the spring.",
        "If the schedule holds, the farm will deliver its first power in July 2027, in time for "
        "the summer peak.",
    ],
)

TIMELINE_2 = (
    "Timeline",
    [
        "The schedule has slipped by two months. Ground tests found deeper frost heave than "
        "expected on the rail yard, so the foundations need longer piles.",
        "Site preparation now starts in March 2027, and the first power is expected in September "
        "2027 instead of July. The co-operative says the cost of the longer piles fits within the "
        "existing contingency fund.",
    ],
)

SITE = (
    "Cleaning up the rail yard",
    [
        "The rail yard has been empty for twelve years, and parts of its soil hold diesel and "
        "metal residues. Contractors will remove the worst of it before any foundations go in.",
        "Under the panels, the co-operative will plant two hectares of native wildflowers. The "
        "meadow is meant to feed pollinators and keep weeds down without herbicides.",
    ],
)

SIGNUPS = (
    "Subscriptions open",
    [
        "Sign-ups opened on the 10th of November. In the first week, three hundred and forty "
        "households subscribed, about a third of the farm's capacity.",
        "The co-operative has set aside one in ten shares for households on low incomes, at half "
        "the monthly price. Those shares are allocated by lottery at the end of December.",
    ],
)

EDITIONS = [
    {
        "label": "Edition 1: first published",
        "change": "The story as first published.",
        "sections": [OVERVIEW, SUBSCRIPTION, FUNDING, TIMELINE_1, SITE],
    },
    {
        "label": "Edition 2: the timeline slips",
        "change": "Only the Timeline section changes: first power moves from July to September.",
        "sections": [OVERVIEW, SUBSCRIPTION, FUNDING, TIMELINE_2, SITE],
    },
    {
        "label": "Edition 3: sign-ups open",
        "change": "A new section, Subscriptions open, is added. The rest is as in edition 2.",
        "sections": [OVERVIEW, SUBSCRIPTION, SIGNUPS, FUNDING, TIMELINE_2, SITE],
    },
]
