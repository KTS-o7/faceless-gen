# Plan 08 — Frontend Editorial Wizard

> **Goal:** Build the multi-stage editorial wizard UI — project creation, angle selection, story editing, scene editing — as a stepper-based flow in the React dashboard. Users can edit, reorder, and regenerate fields at each stage before proceeding.

**Assumes:** Plans 01–07 complete. Backend running on port 8000.  
**New frontend dependencies:** `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`

---

## Task 1: Install New Frontend Dependencies

**Actionables:**
- From the `frontend/` directory: `bun add @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities`
- Verify the packages resolve: `bun run build` should still pass after install

**Acceptance Criteria:**
- `bun run build` exits 0 after install
- `import { DndContext } from "@dnd-kit/core"` resolves without TypeScript error

---

## Task 2: Extend API Client

**Actionables:**
- Add the following functions to `frontend/src/lib/api.ts`, all using relative `/api` paths:
  - `createProject(name, source_doc, target_duration_minutes) -> Promise<ProjectDetail>`
  - `listProjects() -> Promise<ProjectSummary[]>`
  - `getProject(id) -> Promise<ProjectDetail>`
  - `deleteProject(id) -> Promise<void>`
  - `generateAngles(projectId) -> Promise<AngleResponse[]>`
  - `chooseAngle(projectId, angleId) -> Promise<AngleResponse>`
  - `generateStory(projectId) -> Promise<StoryBlockResponse[]>`
  - `getStory(projectId) -> Promise<StoryBlockResponse[]>`
  - `reorderStory(projectId, orderedIds) -> Promise<StoryBlockResponse[]>`
  - `updateStoryBlock(projectId, blockId, content) -> Promise<StoryBlockResponse>`
  - `deleteStoryBlock(projectId, blockId) -> Promise<void>`
  - `confirmStory(projectId) -> Promise<ProjectSummary>`
  - `generateScenes(projectId) -> Promise<SceneResponse[]>`
  - `getScenes(projectId) -> Promise<SceneResponse[]>`
  - `reorderScenes(projectId, orderedIds) -> Promise<SceneResponse[]>`
  - `updateScene(projectId, sceneId, fields) -> Promise<SceneResponse>`
  - `regenerateField(projectId, sceneId, fieldName, storyContext, sourceDocExcerpt) -> Promise<SceneResponse>`
  - `confirmScenes(projectId) -> Promise<ProjectSummary>`
- Add TypeScript interfaces matching the backend response schemas: `ProjectSummary`, `ProjectDetail`, `AngleResponse`, `StoryBlockResponse`, `SceneResponse`
- All functions throw a descriptive `Error` on non-ok HTTP responses

**Acceptance Criteria:**
- `bun run build` passes with no TypeScript errors after adding all functions and types
- `listProjects()` with the backend running returns an array without error
- All function signatures match the backend route contracts (correct method, path, body shape)

---

## Task 3: Navigation Restructure

**Actionables:**
- Update `frontend/src/App.tsx` and `frontend/src/components/Layout.tsx` to support a sidebar-style navigation:
  - Top-level nav items: `Projects` and `Settings`
  - When a project is open, show a secondary section in the sidebar titled with the project name, with 5 sub-items: `1. Angles`, `2. Story`, `3. Scenes`, `4. Music`, `5. Generate`
  - Each sub-item shows a status icon: locked (grey lock), active (blue dot), or complete (green checkmark)
  - Sub-items are locked if the project's `stage` hasn't reached them yet
  - Active project is stored in `App.tsx` state as `activeProject: ProjectDetail | null`
- The old "Generate" top-level nav item is removed — generation now lives inside a project

**Acceptance Criteria:**
- `Projects` and `Settings` nav items render correctly
- Opening a project shows the 5-step sub-navigation in the sidebar
- Clicking a locked step does nothing (no navigation)
- Active step is visually highlighted
- `bun run build` passes

---

## Task 4: Projects List View

**Actionables:**
- Create `frontend/src/components/ProjectsList.tsx`
- Fetches `listProjects()` on mount, polls every 5 seconds
- "New Project" button opens a modal/panel (inline, not a browser dialog) with:
  - Project name text input (required)
  - Target duration slider: 1–15 minutes, labeled with current value (e.g. "5 minutes")
  - Markdown doc upload: a `<textarea>` labeled "Paste research doc (Markdown)" — user pastes the full markdown content
  - "Create Project" button — disabled until name and doc are non-empty
  - On submit: calls `createProject()`, closes the panel, opens the new project at step 1 (Angles)
- Each existing project shown as a card with: name, stage badge (colored per stage), `created_at` relative time (e.g. "2 hours ago"), "Open" button, "Delete" button with confirmation
- Empty state when no projects exist

**Acceptance Criteria:**
- New project modal appears on button click, disappears on "Create Project" or cancel
- Duration slider shows current value as a label
- "Create Project" button is disabled when name or doc is empty
- After creation, the new project opens at the Angles step
- Delete button shows a confirm dialog before calling `deleteProject()`
- Projects list refreshes after create or delete

---

## Task 5: Step 1 — Angles View

**Actionables:**
- Create `frontend/src/components/wizard/AnglesStep.tsx`
- On mount: if `project.angles` is empty, automatically call `generateAngles()` and show a loading skeleton
- If angles already exist in project, show them immediately without re-generating
- Render 3 angle cards in a row (or stacked on narrow screens), each showing: `title` (bold), `pitch` (2 lines), a "Choose This Angle" button
- The currently chosen angle (if any) has a distinct visual treatment: green border, a checkmark, button changes to "Chosen"
- "Regenerate Angles" button at the top — calls `generateAngles()` again, replaces the 3 cards (with loading state during the call)
- "Regenerate Angles" is disabled while generation is in progress
- Once an angle is chosen, a "Continue to Story" button appears at the bottom
- "Continue to Story" calls `chooseAngle()` if not already chosen, then navigates to step 2

**Acceptance Criteria:**
- Angles load automatically on first visit (no manual "load" button)
- Choosing an angle highlights it and shows the continue button
- "Regenerate Angles" replaces the existing angles with a loading state
- "Continue to Story" is only visible after an angle is chosen
- `bun run build` passes

---

## Task 6: Step 2 — Story Editing View

**Actionables:**
- Create `frontend/src/components/wizard/StoryStep.tsx`
- On mount: if `project.story_blocks` is empty, automatically call `generateStory()` and show a loading skeleton of placeholder blocks
- Render story blocks as a vertically stacked drag-and-drop list using `@dnd-kit/sortable`
- Each story block is a card with:
  - A drag handle icon on the left (grab cursor)
  - The content as an editable `<textarea>` — auto-resizes to content height, saves on blur via `updateStoryBlock()`
  - A delete button (trash icon) — removes the block immediately in local state, calls `deleteStoryBlock()` async in background
  - A subtle block number label (e.g. "Block 3")
- When the order changes via drag-and-drop, call `reorderStory()` with the new ID order
- "Regenerate Story" button — re-calls `generateStory()`, replaces all blocks (confirm dialog before doing so since it destroys edits)
- "Confirm Story & Continue" button at the bottom — disabled if fewer than 2 blocks exist, calls `confirmStory()`, navigates to step 3

**Acceptance Criteria:**
- Story blocks load automatically on first visit
- Dragging a block and releasing updates the visual order immediately (optimistic)
- `reorderStory()` is called after drag ends with the new ordered ID list
- Editing a block and clicking away saves the content to the backend
- Deleting a block removes it from the UI immediately
- "Confirm Story" is disabled with fewer than 2 blocks
- `bun run build` passes

---

## Task 7: Step 3 — Scene Editing View

**Actionables:**
- Create `frontend/src/components/wizard/ScenesStep.tsx`
- On mount: if `project.scenes` is empty, automatically call `generateScenes()` with a loading skeleton
- Render scenes as a vertically stacked drag-and-drop list using `@dnd-kit/sortable`
- Each scene is an expandable card. Collapsed state shows: scene number, title (editable inline), drag handle. Expanded state shows all 4 fields:
  - `title` — text input
  - `dialog` — textarea
  - `image_prompt` — textarea with a "Regenerate" icon button
  - `video_prompt` — textarea with a "Regenerate" icon button
- Each "Regenerate" icon button (refresh icon) calls `regenerateField()` for that specific field on that scene. Show a spinner on that button while pending. Update the field's textarea with the returned value on success.
- `dialog` field does NOT have a regenerate button (it is pure editorial text derived from the story — user edits it manually)
- All field edits save on blur via `updateScene()`
- Drag-to-reorder calls `reorderScenes()` after drag ends
- Aspect ratio selector: a segmented control with 3 options — `16:9`, `9:16`, `1:1`. Selected value updates the project via `PATCH /api/projects/{id}`. This is shown once at the top of the scenes view, not per-scene.
- "Confirm Scenes & Continue" button at the bottom — disabled if fewer than 2 scenes or no aspect ratio selected. Calls `confirmScenes()`, navigates to step 4.

**Acceptance Criteria:**
- Scene cards expand/collapse on click
- Regenerate button on `image_prompt` shows spinner while loading, then replaces the textarea content
- `dialog` field has no regenerate button
- Aspect ratio selector persists the choice to the backend and re-reads it on page load
- "Confirm Scenes" is disabled without an aspect ratio selected
- Drag reorder calls `reorderScenes()` with the new ID order
- `bun run build` passes

---

## Task 8: Loading, Error, and Empty States

**Actionables:**
- Create `frontend/src/components/wizard/WizardSkeleton.tsx` — a reusable loading skeleton that mimics the shape of the content being loaded (e.g. 3 card skeletons for angles, N block skeletons for story). Uses a CSS pulse animation.
- All 3 wizard step components must use `WizardSkeleton` during initial data load
- All API calls in wizard steps must have error handling: catch errors, display a red inline error message with a "Retry" button below the skeleton
- The "Retry" button re-calls the failed API function
- If the backend returns a 422 (LLM parse error), show a specific message: "The AI returned an unexpected response. Try regenerating."

**Acceptance Criteria:**
- Skeleton renders during all async loads in steps 1, 2, and 3
- Network error shows inline error message with retry button
- 422 response shows the specific "unexpected response" message
- Retrying after an error re-calls the appropriate function

---

## Task 9: Wire Wizard into App.tsx

**Actionables:**
- Update `App.tsx` to:
  - Track `activeProject: ProjectDetail | null` and `activeStep: number | null` in state
  - `openProject(project)` function: sets `activeProject`, determines `activeStep` from the project's `stage` field using a mapping (`angle_selection → 1`, `story_editing → 2`, `scene_editing → 3`, `music_selection → 4`, `generating|done|failed → 5`)
  - When `activeProject` is set, show the wizard step corresponding to `activeStep`
  - Step advancement (from "Continue" buttons) calls `setActiveStep(n + 1)` and also refreshes the project from `getProject()` so stage is up to date
  - Closing a project (via a back button or navigating to Projects list) sets `activeProject = null`

**Acceptance Criteria:**
- Opening a project that is at `scene_editing` stage shows step 3 directly (not step 1)
- Opening a fresh project starts at step 1
- Clicking "Continue" in step 1 transitions to step 2 without a full page reload
- Navigating to the Projects list while a project is open clears `activeProject`

---

## Task 10: Build Verification + Commit

**Actionables:**
- Run `bun run build` inside `frontend/` — fix all TypeScript and build errors
- Start the full stack (`uvicorn` + `bun run dev`) and manually exercise the wizard end-to-end:
  - Create a new project with a short test markdown doc
  - Generate and choose an angle
  - Generate story, reorder two blocks, edit one block's content
  - Confirm story
  - Generate scenes, expand a card, regenerate an `image_prompt`
  - Set aspect ratio
  - Confirm scenes
- Verify all UI states (loading, error, empty, populated) render without console errors
- Commit all frontend files with message: `feat: editorial wizard UI — angles, story, scene steps with drag-and-drop and per-field regen`
- Push to origin

**Acceptance Criteria:**
- `bun run build` → exits 0, no TypeScript errors
- Full wizard flow completes without console errors
- `git push` succeeds

---

## Plan 08 Checklist — Before Moving to Plan 09

- [ ] `bun run build` → exits 0
- [ ] Creating a project and completing all 3 wizard steps works end-to-end
- [ ] Drag-to-reorder works for both story blocks and scenes
- [ ] Per-field regenerate works for `image_prompt` and `video_prompt`
- [ ] Aspect ratio choice persists after page reload
- [ ] Opening a project mid-flow lands on the correct step
- [ ] All loading/error/empty states render without console errors

**Next:** `docs/plans/09-music-and-generation.md`
