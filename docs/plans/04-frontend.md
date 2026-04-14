# Plan 04 — React Frontend (Vite + Bun)

> **Goal:** Build the full dashboard UI — prompt input, live SSE progress log, scene thumbnail strip, video player, job history, settings panel. No auth, no Firebase, local-only.

**Assumes:** Plans 01–03 complete. FastAPI running on port 8000. Bun installed.  
**Stack:** React 18 + TypeScript, Vite, Bun runtime, Tailwind CSS v4, Framer Motion, Lucide icons, sonner (toasts)

---

## Task 1: Scaffold Vite + React + TypeScript Project

**Actionables:**
- From the project root, scaffold a Vite React TS project into the `frontend/` directory: `bun create vite frontend --template react-ts`
- Change into `frontend/` and install base dependencies: `bun install`
- Install additional packages: `tailwindcss`, `@tailwindcss/vite`, `framer-motion`, `lucide-react`, `clsx`, `sonner`
- Install dev dependency: `@types/node`
- Update `frontend/vite.config.ts`:
  - Add the `@tailwindcss/vite` plugin (Tailwind v4 Vite integration)
  - Add a dev server proxy so `/api` and `/outputs` requests are forwarded to `http://localhost:8000` — this avoids CORS issues in development
  - Set dev server port to `5173`
- Replace `frontend/src/index.css` with a single `@import "tailwindcss"` line (Tailwind v4 syntax)
- Verify the dev server starts: `bun run dev`

**Note on Tailwind version:** This project uses Tailwind v4 which ships `@tailwindcss/vite` as its Vite integration. There is no separate `tailwind.config.js` file needed. Confirm the version installed is v4.x before proceeding.

**Acceptance Criteria:**
- `bun run dev` starts without errors and `http://localhost:5173` loads in browser
- Network tab confirms `/api/health` proxies to `http://localhost:8000/health`
- No Tailwind config file errors; utility classes render correctly in the browser
- `bun run build` completes without TypeScript or build errors

---

## Task 2: Type Definitions

**Actionables:**
- Create `frontend/src/types.ts` defining:
  - `JobStatus` — a union type of the four string literals: `pending`, `running`, `done`, `failed`
  - `Job` interface — all fields matching the backend `Job` Pydantic model: `job_id`, `status`, `user_prompt`, `progress_log`, `final_output`, `scene_thumbnails`, `video_paths`, `error`, `created_at`
  - `GenerateSettings` interface — `model` (string), `voice_id` (string), `clip_count` (number), `video_backend` (string)
- All types must exactly match the backend response shapes — no optional fields that the backend always returns

**Acceptance Criteria:**
- `bun run build` passes with no TypeScript errors after adding types
- A `Job` object returned from `GET /api/history` can be assigned to `Job` without type errors
- `JobStatus` type prevents assigning arbitrary strings (TypeScript error on `"unknown"`)

---

## Task 3: API Client

**Actionables:**
- Create `frontend/src/lib/api.ts` with the following exported functions, all using `fetch` against `/api` (relative, proxied by Vite in dev):
  - `startGeneration(prompt: string) -> Promise<{job_id: string, status: string}>` — POST to `/api/generate`
  - `getHistory() -> Promise<Job[]>` — GET `/api/history`
  - `getJob(jobId: string) -> Promise<Job>` — GET `/api/history/{jobId}`
  - `streamJobProgress(jobId, onProgress, onDone, onError) -> () => void` — opens an `EventSource` to `/api/generate/{jobId}/stream`, attaches listeners for `progress`, `done`, and `error` named events, returns a cleanup function that calls `es.close()`
- All fetch functions must throw a descriptive `Error` on non-ok HTTP responses, including the status code and status text

**Acceptance Criteria:**
- `startGeneration("test")` with the backend running returns an object with `job_id` string
- `getHistory()` returns an array (possibly empty)
- `streamJobProgress` cleanup function closes the `EventSource` without error
- On a 404 response, `getJob` throws `Error` with the status in the message

---

## Task 4: Hooks

**Actionables:**
- Create `frontend/src/hooks/useGenerate.ts`:
  - State: `isGenerating` (bool), `progressLog` (string[]), `currentJob` (Job | null), `error` (string | null)
  - `generate(prompt: string)` async function: clears previous state, calls `startGeneration`, then calls `streamJobProgress` to stream progress
  - `cancel()` function: closes the SSE stream and sets `isGenerating` to false
  - Store the SSE cleanup function in a `useRef` so it persists across renders and is called on unmount
  - On `onProgress`: append message to `progressLog`
  - On `onDone`: set `currentJob`, set `isGenerating` to false
  - On `onError`: set `error`, set `isGenerating` to false
- Create `frontend/src/hooks/useHistory.ts`:
  - State: `jobs` (Job[]), `loading` (bool)
  - On mount: call `getHistory()` and set jobs
  - Auto-refresh every 4 seconds while the component is mounted
  - Expose a `refresh()` function for manual refresh
  - Clear the interval on unmount

**Acceptance Criteria:**
- `useGenerate`: calling `generate()` sets `isGenerating = true`; `onDone` callback sets `isGenerating = false` and populates `currentJob`
- `useGenerate`: calling `cancel()` closes the stream and sets `isGenerating = false`
- `useHistory`: `loading` is `true` initially, `false` after first fetch
- `useHistory`: `refresh()` triggers a new `getHistory()` call
- No memory leaks: SSE `EventSource` and history interval are both cleaned up on unmount

---

## Task 5: Layout Component

**Actionables:**
- Create `frontend/src/components/Layout.tsx`
- Full-height dark layout (`bg-zinc-950`, white text)
- Header with: app icon (orange accent), "Faceless-Gen" title, subtitle "Local AI Video Studio"
- Navigation bar in the header with three buttons: Generate, History, Settings — the active view has a distinct background highlight
- Navigation fires an `onNavigate(view)` callback prop
- `children` renders in a centered, max-width content area below the header

**Acceptance Criteria:**
- All three nav buttons render and are clickable
- Active view button is visually distinct from inactive ones
- Content area is centered with consistent padding on all screen sizes
- Layout renders without console errors

---

## Task 6: GenerateForm Component

**Actionables:**
- Create `frontend/src/components/GenerateForm.tsx`
- A textarea for the video prompt (multi-line, placeholder text, resizes vertically, disabled when `isGenerating`)
- A dropdown to select the LLM model — options: `glm-5`, `gpt-4o`, `claude-3-5-sonnet-20241022`, `gemini-2.0-flash`
- A Generate button that:
  - Is disabled when prompt is empty or `isGenerating` is true
  - Shows a spinner + "Generating..." text while `isGenerating`
  - Shows a spark icon + "Generate" text when idle
- Calls `onGenerate(prompt)` on click

**Acceptance Criteria:**
- Button is disabled with empty prompt
- Button is disabled while `isGenerating` is true
- Button text changes between idle and generating states
- Textarea is disabled while generating
- Component renders without console errors

---

## Task 7: ProgressLog Component

**Actionables:**
- Create `frontend/src/components/ProgressLog.tsx`
- Returns `null` when `logs` is empty and `isActive` is false
- Displays a terminal-style scrollable log container (max height, monospace font, dark background)
- Animates each new log entry appearing using `framer-motion` (slide in from left, fade in)
- Shows a pulsing "Running" indicator badge when `isActive` is true
- Auto-scrolls to the bottom when new log entries are added (use `useRef` + `scrollIntoView`)

**Acceptance Criteria:**
- Returns nothing when logs are empty and not active
- Each new log entry animates in (verify via Framer Motion `initial`/`animate` props)
- Container scrolls to the latest entry automatically
- "Running" badge is visible when `isActive=true`, hidden when false

---

## Task 8: VideoCard Component

**Actionables:**
- Create `frontend/src/components/VideoCard.tsx` accepting a `Job` prop
- Status badge in the top-right corner with distinct colors per status: yellow (pending), blue+spinner (running), green (done), red (failed)
- If `scene_thumbnails` has entries: render a horizontal scrollable strip of thumbnail images using URLs `/outputs/{job_id}/thumb_NN.jpg`
- Image `onError` handler hides broken images gracefully (set display:none)
- Prompt text truncated to 2 lines with ellipsis
- If `status === "done"` and `final_output` is set: render an HTML5 `<video>` element with `controls`, source `/outputs/{job_id}/final.mp4`
- If `error` is set: render the error in a red monospace box
- Use `framer-motion` `layout` and entrance animation

**Acceptance Criteria:**
- Status badge renders with the correct color for each of the 4 statuses
- Thumbnail images render when `scene_thumbnails` is non-empty
- Broken thumbnail images are hidden (onError handler works)
- Video player renders only when `status === "done"` and `final_output` is set
- Error box renders only when `error` is set
- Component renders without console errors for a job in each status

---

## Task 9: VideoHistory Component

**Actionables:**
- Create `frontend/src/components/VideoHistory.tsx`
- Uses the `useHistory` hook
- Shows a "Loading..." state while `loading` is true
- Shows an empty state illustration + message when `jobs` is empty
- Renders jobs in a 2-column responsive grid using `VideoCard` for each
- Refresh button in the header that calls `refresh()` from the hook

**Acceptance Criteria:**
- "Loading..." appears on initial render before jobs load
- Empty state shows when history is empty
- Jobs render in the grid
- Refresh button triggers a new history fetch

---

## Task 10: SettingsView Component

**Actionables:**
- Create `frontend/src/components/SettingsView.tsx`
- Two settings sections: LLM model (text input defaulting from `localStorage`) and ElevenLabs Voice ID (text input defaulting from `localStorage`)
- A "Save Preferences" button that writes the values to `localStorage`
- A clear disclaimer that these are UI preferences only — to change API keys, edit `.env` and restart the server
- Do not show any actual API key fields — they are backend-only

**Acceptance Criteria:**
- Inputs are pre-populated from `localStorage` on mount (or show defaults if nothing saved)
- Save button writes values to `localStorage` (verify with `localStorage.getItem(...)`)
- No API key fields are shown
- Component renders without console errors

---

## Task 11: Wire Up App.tsx

**Actionables:**
- Rewrite `frontend/src/App.tsx` to:
  - Manage current view state: `generate`, `history`, `settings`
  - Use `useGenerate` hook at the top level
  - Render `Layout` wrapping the active view
  - Generate view: render `GenerateForm`, `ProgressLog`, and on completion a `VideoCard` for the finished job
  - Error display: if `error` is set, show it in a styled red box above the progress log
  - History view: render `VideoHistory`
  - Settings view: render `SettingsView`
  - Include `<Toaster>` from sonner at the root for future toast notifications

**Acceptance Criteria:**
- All three views render when their nav button is clicked
- Generate view shows the form, then progress log during generation, then result card on completion
- No console errors on any view
- `bun run build` passes with no TypeScript errors

---

## Task 12: Cleanup and Polish

**Actionables:**
- Remove Vite boilerplate: delete `frontend/src/assets/react.svg`, `frontend/public/vite.svg`, default CSS from `App.css`
- Update `frontend/index.html` title to `Faceless-Gen`
- Verify that thumbnails and video files are served correctly via the `/outputs` proxy in dev mode
- Verify that the video player loads `final.mp4` for a completed job

**Acceptance Criteria:**
- No Vite placeholder content visible in the app
- Page title is "Faceless-Gen"
- A completed job's thumbnail strip loads images without 404s
- A completed job's video player loads and plays the MP4

---

## Task 13: Full Stack End-to-End Test

**Actionables:**
- In Terminal 1: start the backend — `source .venv/bin/activate && uvicorn backend.main:app --reload --port 8000`
- In Terminal 2: start the frontend — `cd frontend && bun run dev`
- Open `http://localhost:5173` in browser
- Submit a prompt, observe the progress log filling in via SSE
- Navigate to History — the job appears
- Once done, the video card in the Generate view shows thumbnails and the video player
- Navigate to Settings, change a preference, reload — preference persists

**Acceptance Criteria:**
- Prompt submission triggers SSE progress events visible in the UI in real time
- Completed job card shows scene thumbnails and a working video player
- History view shows the completed job
- Settings persist across page reloads via localStorage
- No console errors during normal usage flow

---

## Task 14: Commit

**Actionables:**
- Run `bun run build` inside `frontend/` — fix any TypeScript or build errors before committing
- From project root: stage all frontend files and commit with message: `feat: React + Vite + Bun dashboard — generate form, SSE progress, history, settings`
- Push to origin

**Acceptance Criteria:**
- `bun run build` exits with code 0, no TypeScript errors
- `git push` succeeds
- `frontend/dist/` is gitignored and not committed

---

## Plan 04 Final Checklist — All Plans Complete

- [ ] `bun run build` (in `frontend/`) → exits 0, no TypeScript errors
- [ ] `bun run dev` → `http://localhost:5173` loads the dashboard
- [ ] Submitting a prompt streams SSE progress into the UI in real time
- [ ] Completed job shows scene thumbnails and video player
- [ ] History view shows all past jobs
- [ ] Settings view reads/writes from localStorage
- [ ] `pytest backend/tests/ -v` → all backend tests still pass
- [ ] `http://localhost:8000/docs` → all API endpoints documented

---

## How to Swap Models (Quick Reference)

**Change LLM model:**
- Edit `.env`: set `BIFROST_MODEL=gpt-4o`
- Restart uvicorn — no code changes needed

**Switch to cloud video generation:**
- Edit `.env`: set `VIDEO_BACKEND=cloud`, fill `CLOUD_VIDEO_API_KEY` and `CLOUD_VIDEO_BASE_URL`
- Implement `CloudVideoBackend.generate_clip()` in `backend/providers/video_backend.py`

**Change TTS voice:**
- Edit `.env`: set `ELEVENLABS_VOICE_ID=<new_id>`
- Find voice IDs at `elevenlabs.io/voice-library`
