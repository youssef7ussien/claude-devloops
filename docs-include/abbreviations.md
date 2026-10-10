*[acceptance criterion]: A statement that must be true for a milestone to pass; validation checks each one.
*[approval]: Accepting a plan so that building can start, by you or automatically.
*[assumption]: A decision Claude Code made where the requirements say nothing, recorded for review.
*[backend-dev]: The loop that builds an HTTP API, validated with real HTTP requests.
*[call]: One run of Claude Code for one step, recorded with its prompt, conversation, tokens and cost.
*[check]: An HTTP request and the answer it must get, written before a backend milestone's code.
*[contract]: The backend's OpenAPI document: the operations the API offers.
*[dashboard]: The web page devloops serves to show a workspace.
*[evidence]: What validation keeps to show what it saw: HTTP answers, screenshots, network requests.
*[export]: The dashboard written as one HTML file with all its data inside.
*[frontend-dev]: The loop that builds the user interface, validated in a real browser.
*[handoff]: What the backend loop passes to the frontend loop: its OpenAPI document and how to start it.
*[headless Claude Code]: Claude Code run as a command (claude -p), without its interactive screen.
*[loop]: One of devloops' two ways of building, backend-dev or frontend-dev.
*[milestone]: A part of the application built and validated on its own, one at a time.
*[open question]: Something the requirements leave unclear, which Claude Code asks about.
*[plan]: The milestones, tasks and acceptance criteria devloops builds from the requirements.
*[project]: A folder set up for devloops with devloops init.
*[requirements]: The written description of what to build.
*[retry grant]: More trials for a failed milestone, given with devloops retry.
*[runtime]: How to start and reach the application while it is validated.
*[stand-in]: A program that answers in place of Claude Code, for tests and examples.
*[step]: One kind of call to Claude Code: plan, replan, author-checks, implement, fix or validate-ui.
*[story]: One user story: a small piece of the requirements, from a user's point of view.
*[suggested answer]: Claude Code's proposed answer to an open question.
*[target]: The folder a loop writes the application's code to; the only place Claude Code may write.
*[task]: One piece of work inside a milestone.
*[trial]: One attempt at a milestone: write or fix the code, then validate it.
*[validation]: devloops' own test of a trial's result, never Claude's word.
*[workspace]: The folder that holds everything about one run.
