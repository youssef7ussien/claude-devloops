# Product Requirements Document


## 1. Product Overview

A personal productivity application that unifies task management, habit tracking, learning-resource tracking, and structured planning into one workspace.

Beyond simple task/habit tracking, QuickFlow lets a user pull together previously-created tasks, habits, and learning resources into a Plan - a scheduled block of work with an estimated duration, a start/end date-time window, and a priority order. The app then tracks each plan's live progress and remaining ("rest") time on the Todo Plans page, and rolls every plan's item-level completion up into a dashboard summary.

## 2. Goals

### Primary Goals
- Provide a fast, simple task-management experience.
- Allow users to track recurring habits.
- Allow users to track learning resources, each with its own milestones and notes.
- Let users assemble tasks, habits, and learning resources into time-boxed Plans with estimated duration, start/end date-time, and priority order.
- Visualize each plan's live progress and remaining ("rest") time, from its scheduled start until its end.
- Give users one dashboard summarizing all of the above.
- Keep the MVP small enough to implement and test quickly.

### Non-Goals
- Team collaboration
- Real-time chat
- Calendar synchronization with external calendar providers
- File attachments
- Social networking
- Advanced AI functionality

## 3. Target User

A single individual who wants one application to manage daily work, recurring habits, learning progress, and time-boxed plans built from that content.

## 4. Application Structure

The application contains six top-level pages, each independently reachable from persistent navigation:

1. Dashboard - summary view across all features.
2. Tasks - create, edit, complete, archive, delete tasks.
3. Habits - create, edit, complete, deactivate, delete recurring habits.
4. Learning Resources - create/remove learning cards; each card holds milestones and notes.
5. Todo Plans - build a scheduled plan from existing tasks, habits, and learning resources; visualize each plan's live progress and remaining ("rest") time.
6. Settings - user/account and application preferences.

## 5. User Stories

### Tasks
- As a user, I want to create a task.
- As a user, I want to edit a task.
- As a user, I want to mark a task as completed.
- As a user, I want to delete or archive a task.
- As a user, I want to filter tasks by status and priority.
- As a user, I want to search my tasks.
- As a user, I want to see overdue tasks.

### Habits
- As a user, I want to create a recurring habit.
- As a user, I want to choose daily or weekly recurrence.
- As a user, I want to mark a habit complete for today.
- As a user, I want to see my current habit completion progress.
- As a user, I want to remove a habit I no longer track.

### Learning Resources
- As a user, I want to add a learning resource as a card (e.g. a course, book, or topic).
- As a user, I want to remove a learning card I no longer need.
- As a user, I want to add milestones under a learning card to break it into steps.
- As a user, I want to mark milestones complete.
- As a user, I want to attach free-form notes to a learning card.

### Todo Plans
- As a user, I want to create a plan by selecting existing tasks, habits, and/or learning resources.
- As a user, I want to set an estimated time for a plan.
- As a user, I want to set a start date/time and an end date/time for a plan.
- As a user, I want to set a priority order for a plan relative to other plans.
- As a user, I want to mark individual items inside a plan as done, independent of the plan's overall status.
- As a user, I want to remove a plan.
- As a user, I want to be notified when a plan's scheduled start time arrives.
- As a user, I want to see a live "rest time" (time remaining) indicator for an in-progress plan, updating continuously from start until end.
- As a user, I want to see a plan's completion progress, based on how many of its items are marked done.
- As a user, I want a history of past plans and how much of each was completed.

### Dashboard
- As a user, I want to see today's tasks immediately after opening the app.
- As a user, I want to see overdue tasks.
- As a user, I want to see today's habits.
- As a user, I want to see a simple completion percentage.
- As a user, I want to see active/in-progress plans and their rest time at a glance.
- As a user, I want to see a snapshot of learning progress.

## 6. Functional Requirements

### FR-01 Task Management
A task shall contain:
- Id
- Title
- Description
- Status (Todo, In Progress, Done)
- Priority (Low, Medium, High)
- DueDate
- CreatedAt
- UpdatedAt
- IsArchived

The user shall be able to create, read, update, archive, restore, and delete tasks.

### FR-02 Task Search and Filtering
The application shall support:
- Free-text search by title.
- Status filter.
- Priority filter.
- Due-date filter.
- Sorting by due date or creation date.

### FR-03 Habit Management
A habit shall contain:
- Id
- Name
- Description
- Frequency (Daily, Weekly)
- CreatedAt
- IsActive

The user shall be able to create, update, deactivate, and delete habits.

### FR-04 Habit Completion
The system shall record a completion event containing:
- Id
- HabitId
- CompletionDate

A user shall be able to mark a habit complete for a date. Duplicate completion records for the same habit/date shall be prevented.

### FR-05 Learning Resources
A learning card shall contain:
- Id
- Title
- Description / source (e.g. link, book, course name)
- CreatedAt
- Status (Not Started, In Progress, Completed)

The user shall be able to add and remove learning cards.

### FR-06 Learning Milestones and Notes
Each learning card shall support:
- A list of milestones, each with a title, an IsDone flag, and an optional target date.
- A list of free-form notes, each with text content and a timestamp.

The user shall be able to add, complete, and remove milestones, and add and remove notes, under a given learning card.

### FR-07 Plan Composition (Todo Plans)
A plan shall contain:
- Id
- Title
- A collection of plan items, where each item references an existing task, habit, or learning resource (by Id and type) and carries its own IsDone flag
- EstimatedDuration
- StartDateTime
- EndDateTime
- PriorityOrder (numeric or ordinal ranking relative to other plans)
- Status (Not Started, In Progress, Completed)
- CreatedAt

The user shall be able to:
- Create a plan by selecting one or more existing tasks, habits, and/or learning resources.
- Set the plan's estimated duration, start date/time, end date/time, and priority order.
- Mark an individual plan item done or not done.
- Remove a plan.

### FR-08 Plan Progress and Rest Time
The system shall:
- Notify the user when a plan's StartDateTime is reached.
- From StartDateTime until EndDateTime, continuously compute and display the plan's remaining ("rest") time.
- Compute a plan's completion percentage as (items marked done) / (total items in the plan).
- Update a plan's Status automatically based on current time and item completion (Not Started -> In Progress -> Completed).
- Reflect item-level completion changes immediately in the owning plan's progress, and in the dashboard summary.

### FR-09 Dashboard
The dashboard shall display:
- Tasks due today.
- Overdue tasks.
- Completed tasks today.
- Active habits and habits completed today.
- Task completion percentage.
- Active/in-progress plans with live rest-time and progress.
- A learning-progress snapshot (e.g. cards in progress, milestones completed recently).

## 7. Business Rules

1. Task title is required and has a maximum length of 200 characters.
2. Task description is optional and has a maximum length of 2,000 characters.
3. A task cannot have an invalid status or priority.
4. An archived task is excluded from the default task list.
5. A completed task has status Done.
6. A habit name is required and has a maximum length of 150 characters.
7. A habit can have only one completion record for a specific date.
8. A learning card title is required.
9. A milestone belongs to exactly one learning card.
10. A plan must reference at least one existing task, habit, or learning-resource item.
11. A plan's EndDateTime must be after its StartDateTime.
12. A plan's rest-time display is only active between its StartDateTime and EndDateTime.
13. Marking a plan item done does not alter the completion state of the original task/habit/learning card outside the plan, except where the plan item directly represents that entity's own completion action (e.g. completing a task-type plan item completes the underlying task).
14. Deleted resources cannot be returned by normal queries.

## 8. UX Requirements

### Main Navigation
- Dashboard
- Tasks
- Habits
- Learning Resources
- Todo Plans
- Settings

### Dashboard
1. Greeting/header.
2. Summary metric cards (tasks, habits, plans, learning).
3. Today's task list.
4. Today's habit checklist.
5. Active plans with live progress/rest-time.
6. Quick-add actions.

### Tasks Page
- Search box, status filter, priority filter.
- Add Task action.
- Task list with edit/delete/archive actions.
- Empty state.

### Habits Page
- Add Habit action.
- Habit cards with completion toggle, frequency label, streak indicator.
- Edit/deactivate/remove actions.
- Empty state.

### Learning Resources Page
- Add Learning Card action.
- Card grid; each card expandable to show milestones and notes.
- Add/remove milestone controls; add/remove note controls.
- Empty state.

### Todo Plans Page
- Create Plan action, opening a builder that lets the user pick from existing tasks, habits, and learning resources.
- Fields for estimated duration, start date/time, end date/time, priority order.
- List of plans grouped into active/upcoming and completed, each showing progress (percent complete) and live rest time (remaining time from start to end), with per-item done toggles and remove actions.
- Notification/highlight when a plan's start time is reached.
- Empty state.

### Settings Page
- User/profile information.
- Application preferences (e.g. notification behavior, default view).

## 9. Data Model

### Task
- Id, Title, Description, Status, Priority, DueDate, CreatedAt, UpdatedAt, IsArchived

### Habit
- Id, Name, Description, Frequency, CreatedAt, IsActive

### HabitCompletion
- Id, HabitId, CompletionDate, CreatedAt

### LearningCard
- Id, Title, Description, Status, CreatedAt

### LearningMilestone
- Id, LearningCardId, Title, IsDone, TargetDate

### LearningNote
- Id, LearningCardId, Text, CreatedAt

### Plan
- Id, Title, EstimatedDuration, StartDateTime, EndDateTime, PriorityOrder, Status, CreatedAt

### PlanItem
- Id, PlanId, SourceType (Task | Habit | LearningResource), SourceId, IsDone

Relationships:
- Habit 1:N HabitCompletions
- LearningCard 1:N LearningMilestones
- LearningCard 1:N LearningNotes
- Plan 1:N PlanItems
- PlanItem N:1 (Task | Habit | LearningCard), polymorphic by SourceType/SourceId

Unique constraints:
- (HabitId, CompletionDate)

## 10. Non-Functional Requirements

### Performance
- Typical in-app actions (create/update/delete/filter) should feel instantaneous (under 500 ms).
- Live rest-time indicators shall update at least once per minute while a plan is in progress.

### Reliability
- Application state shall persist reliably between sessions.
- Plan status transitions (Not Started -> In Progress -> Completed) shall be computed consistently from stored start/end times and item completion, even after the app is closed and reopened.

### Usability
- Every list-style page (Tasks, Habits, Learning Resources, Todo Plans) shall support adding and removing items directly from that page.
- Empty states shall guide the user toward the relevant "add" action.

### Maintainability
- Keep domain/business rules testable and separated from presentation.
- Avoid duplicating completion-state logic between a plan item and its source entity beyond what FR-08/Business Rule 13 requires.

## 11. Testing Requirements

- Unit tests for business rules (task/habit/plan validation, rest-time computation, completion roll-up).
- Tests covering plan progress and rest-time transitions across the Not Started -> In Progress -> Completed lifecycle.
- Tests confirming dashboard metrics match underlying task/habit/plan/learning data.
- End-to-end coverage of: create task, complete task, create habit, complete habit, add learning card with milestones, build a plan from existing items, mark plan items done, verify plan achievement and dashboard update accordingly.

## 12. Acceptance Criteria

### Tasks
- User can create, edit, complete, archive, and delete a task.
- Required fields are validated.
- Search and filters work correctly.
- Overdue tasks are identified correctly.

### Habits
- User can create a daily or weekly habit.
- User can complete a habit for today; duplicate completion for the same date is prevented.
- User can deactivate or remove a habit.

### Learning Resources
- User can add and remove a learning card.
- User can add, complete, and remove milestones under a card.
- User can add and remove notes under a card.

### Todo Plans
- User can create a plan from existing tasks, habits, and/or learning resources.
- User can set estimated duration, start/end date-time, and priority order.
- User can mark individual plan items done, and this updates the plan's progress.
- User can remove a plan.
- User is notified when a plan's start time is reached.
- Rest time visibly counts down/updates from the plan's start until its end.
- Plan progress percentage reflects the ratio of done items to total items.
- Item-level completion changes are reflected in both the plan's progress view and the dashboard.

### Dashboard
- Today's tasks, overdue tasks, and today's habits are displayed.
- Completion metrics match the underlying data.
- Active plans display live progress and rest time.
- Learning snapshot reflects current learning-card/milestone state.

## 13. Definition of Done

The MVP is complete when:
- All six pages (Dashboard, Tasks, Habits, Learning Resources, Todo Plans, Settings) are implemented and reachable from persistent navigation.
- Tasks, habits, and learning resources can each be added and removed directly from their respective pages.
- Learning cards support milestones and notes.
- Plans can be built by selecting existing tasks, habits, and learning resources, with estimated duration, start/end date-time, and priority order.
- Plan and item-level completion correctly drives plan progress, rest-time display, and the dashboard summary.
- Automated tests pass.

## 14. Future Enhancements

Possible post-MVP features:
- Tags and categories.
- Recurring task schedules.
- Monthly productivity analytics.
- External calendar integration.
- Email/push reminders beyond in-app notification.
- Drag-and-drop plan/priority reordering.
- Multi-user/team workspaces.
