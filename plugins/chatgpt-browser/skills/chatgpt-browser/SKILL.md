---
name: chatgpt-browser
description: >-
  Operate ChatGPT in a user-authorized interactive browser across models,
  reasoning levels, Projects, ordinary or temporary chats, attachments and
  pasted context, apps and custom GPTs, response waiting, and thread hygiene.
  Use when an agent is asked to interact with ChatGPT through a browser; do
  not use for OpenAI API calls, ordinary web browsing, non-ChatGPT browser
  tasks, or generic second-model review unless the user specifically requests
  ChatGPT in the browser.
---

# ChatGPT Browser

Use ChatGPT through the user's authorized interactive browser while preserving conversation placement, context integrity, and external-effect boundaries.

## Respect ownership and authority

Use the browser the user names. Otherwise use the first suitable capability available on the current host in this order:

1. [@Browser](plugin://browser@openai-bundled)
2. [@chrome](plugin://chrome@openai-bundled)
3. Another suitable host-provided interactive browser other than the lower-tier generic Computer Use or standalone or external Playwright.
4. Generic host-provided Computer Use without assuming a specific plugin.
5. Standalone or external Playwright.
- Skip any named-plugin tier the host does not provide. Follow the selected capability's own mechanics; install or improvise browser control only at the user's request. Playwright-compatible methods exposed inside a selected built-in browser remain part of that browser's tier.
- Reuse the signed-in browser and useful ChatGPT tabs when available.
- If ChatGPT is signed out, ask the user to sign in there and continue once the browser shows them signed in.
- Never request, enter, inspect, or extract passwords, cookies, tokens, local storage, or browser profiles.
- Inspect the live UI. Do not rely on fixed selectors, labels, model catalogs, upload limits, or remembered account capabilities.

Treat effects separately:

- Inspecting account, chat, Project, selection, attachments, and response state is read-only.
- Creating a Project or chat, uploading context, and sending a message are persistent mutations.
- Connect or authorize an app, grant permissions, purchase, publish, or act outward only when the user's request names that action.
- Existing Projects, chats, drafts, files, credentials, grants, and history are protected state. Delete, rename, move, edit, or archive them only at the user's request.
- Before leaving any chat, resolve the loss risk from its unsent draft, pending attachments, or active generation. Do not clear or overwrite pre-existing composer state to make room for the new task.
- If a current tab contains a draft, pending attachment, or active generation, perform fresh work in a different tab object. Verify the tab identities differ before navigation and leave the protected tab unchanged until the user releases it.
- Before creating a tab, inventory the host-owned identities of existing tabs. Track the host-owned identity returned for every tab you create; active-tab position, variable names, worktree identity, URLs, and page labels do not establish ownership.

## Orient before acting

- Inspect the signed-in state, active conversation surface, current Project and chat, chat durability, selected model and reasoning level, selected app or GPT, composer, attachments, and generation state.
- Refresh only when the page is stale or failed, or when the generation-recovery rule below permits it. First protect any unsent draft, pending upload, attachment, or other recoverable state that refresh could lose.
- After refresh, navigation recovery, or a surface switch, reverify the account, active conversation surface, Project and chat, chat durability, model and reasoning level, app or GPT, composer, attachments, and the same turn and generation when applicable.

## Choose the conversation surface

- Treat Chat and Work as distinct conversation surfaces whose available chat durability, temporary-chat behavior, Projects, files, plugins, models, reasoning controls, fast mode, and composer controls may differ.
- Follow the user's explicit Chat or Work choice. Otherwise use Chat.
- Use Work only when the user explicitly requests it, selects an existing Work conversation, or requests a capability available only there.
- If the intended surface or capability cannot be selected and positively verified, report the constraint and do not silently substitute another surface.

## Place the conversation

Apply this precedence:

1. Follow the user's explicit choice of existing chat, new chat, Project, ordinary chat, or temporary chat.
2. Otherwise, enter an unambiguously relevant existing Project and create a fresh chat inside it.
3. If no relevant Project exists and the user asked for a Project without naming another destination, or the work benefits from durable organization because it involves multiple related questions, likely future follow-ups, reusable file context, or long-term continuity, locate and reuse the exact `Temp` Project. If it does not exist, create it, then create a fresh chat inside it.
4. Otherwise, use a temporary chat for disposable work.

- Enter a Project before creating its chat, then visibly verify that the new chat belongs to that Project before sending substantive context.
- Use only an unambiguous Project match. Treat several plausible Projects as none, and reuse the most recent of several exact-name `Temp` Projects.
- Create a task- or domain-oriented Project other than `Temp` only when the user explicitly requests it.
- Prefer multiple focused chats in one Project over one indefinitely growing thread.
- Do not assume another Project chat's discussion or files are active context.
- Prefer a fresh chat to repurposing an existing thread unless the user chose that thread.
- Use an ordinary unprojected chat only when the user explicitly requests one.
- When—and only when—using a temporary chat, select the live option that permits plugins and custom instructions (currently `Personalized`) and positively verify both temporary mode and that selection before sending. If selection or verification fails, do not send. Do not change this setting for an ordinary chat. Treat the temporary chat as disposable and potentially unrecoverable; extract the needed result before leaving.
- Do not claim temporary-chat Project inheritance, file persistence, or recoverability without current visible evidence.
- Start a fresh chat when the subject changes materially, patch history becomes long, files are substantially replaced, stale assumptions repeat, context becomes confused, or answer quality declines. Do not impose a universal turn count.

## Select models, apps, and GPTs

- Unless the user explicitly requests a different selection or asks not to maximize capability, choose the active conversation surface's most capable model and highest reasoning effort compatible with the requested app, GPT, tools, and context. Report any compatibility constraint that prevents this default.
- When a user says to use a label that corresponds to a model, compact preset, or reasoning-effort option, interpret it as that selection. This meaning takes precedence over the same label in account-plan UI; bare `Pro` means the Pro selection unless the user explicitly refers to an account, plan, or subscription.
- Treat the conversation surface, model, and reasoning effort as one composed selection state that may appear as a compact Power preset or as separate advanced Model and Effort controls. An explicitly named dimension wins; otherwise match the requested label against the compact preset and every advanced dimension while preserving unrelated selections.
- Scope matching and verification to the active selector or composer control; account-plan badges and unrelated page text are not selection evidence.
- Never silently substitute or declare a requested selection unavailable until every live selection dimension has been inspected.
- Before sending, require positive visible evidence of the intended selection. If verification is absent or inconclusive, do not send.
- Discover available ChatGPT apps, tools, connectors, and custom GPTs from the live UI.
- Select the exact requested app or GPT and verify its active identity before adding context. Report restrictions it imposes on models, tools, or context.
- Never silently replace an unavailable app or GPT.
- Install apps or send messages only when the user's request names that action. Ask the user to perform sign-in or consent personally and continue once the page shows it done.

## Maintain a reasoning conversation

- Every message you send to ChatGPT SHALL be a conversational, declarative contribution to an ongoing exchange, not an instruction brief or work order. In the opening turn, establish the user's objective, the authorized decision-relevant reality ChatGPT cannot otherwise know, and requirements genuinely fixed by the user or a real consumer interface.
- After that baseline, continue from the shared context. Later turns SHOULD add only new or corrected decision-relevant reality, genuine disagreement, or the live uncertainty worth exploring; repeat the baseline only after context loss, a new chat, or a material state change.
- Speak naturally in your own voice about observations, hypotheses, doubts, proposals, disagreements, and questions. These remain revisable perspectives and SHALL NOT become a persona, forced choice, scope, procedure, agenda, decomposition, response schema or count, completion standard, or any other assignment not established by legitimate authority.
- Let questions arise from the conversation as genuine inquiry. Do not bundle them into an authoritative questionnaire, impose a fixed message template or arbitrary question limit, or turn the exchange into a procedural checklist.
- ChatGPT owns every judgment left open by genuine requirements and, subject only to those requirements, the form of its response. Leave it free to challenge the framing, pursue the issues it finds material, ask its own questions, and decide what best advances the user's objective.

## Supply reliable context

- Before composing the opening turn or rebuilding a baseline, inspect the authorized local task surface and form a candidate inventory. It SHALL include the primary artifacts and every supporting source file, test, configuration, document, log, dataset, image, or other input that could materially affect ChatGPT's judgment and is likely to fit the selected model and live upload surface. Inclusion is the default; do not limit discovery to paths the user happened to name.
- Supply the maximal relevant candidate set as actual attachments or pasted content. A local path, summary, Project membership, or mention does not supply a file; Project placement does not replace message-level attachment unless the identical current file is visibly available to this chat. Avoid duplicate copies of the same current context in one turn.
- Before each later turn, update the inventory for new, changed, or newly relevant files and supply them. Do not reattach unchanged files while the same chat's baseline remains reliable.
- When a plan or artifact is under review, you SHALL supply the complete current artifact. You SHALL NOT replace the reviewed object with a summary, selected questions, or a template for ChatGPT's response.
- Prefer original files in their native formats, especially images and documents, while live count, size, and type limits permit. If those limits block direct supply, create one or more task-scoped temporary ZIP bundles that preserve relative paths and file identity. Split bundles only as observed limits require, never alter the source tree, and remove the temporary bundles after the send/read lifecycle.
- If all relevant context still cannot fit, prioritize the complete current primary artifact followed by its closest decision-relevant dependencies, and report material omissions truthfully to the caller.
- Do not tell ChatGPT to read, inspect, open, unpack, or use supplied files, and do not explain how to do so. Do not summarize a file as a substitute for supplying it; attach it and continue the conversation naturally. Mention file identity or revision only when needed to disambiguate the context.
- Before sending, compare the candidate inventory with the final composer and attachment tray, then verify filenames, attachment count, previews, and completed uploads. Do not send while an avoidable relevant candidate is omitted, an upload failed, or attachment identity remains uncertain. Remove only duplicate or stale attachments you added; leave attachments that were already present unchanged.
- Compare the before/after attachment inventory before removing anything; treat an attachment with uncertain identity as pre-existing protected state.
- When identity matters, add a filename plus revision, digest, inventory, or unique marker and verify it from the attachment surface.
- Keep short text inline. Long pasted text may appear as an attachment-like pill, currently familiar as `Pasted text`; this still supplies the text, so do not repaste it merely because it left the visible composer body.
- Inspect the whole composer and attachment tray; an unchanged editable text body does not prove that a paste or attachment failed.
- Expect images and documents to appear as thumbnails, filename pills, or previews. Wait for processing to finish before sending.
- When starting or moving to a fresh chat, supply the complete current baseline. Use patches only while that baseline remains reliable, identifying each patch's base revision and affected files. When patches accumulate, files are substantially replaced, or state is lost, resend the complete current baseline rather than extend the patch history.
- Exclude credentials, secrets, browser data, generated dependencies, build outputs, duplicates, stale revisions, and irrelevant history.

## Send, wait, and return the result

- Recognize that sending can permanently retain the prompt and attachments.
- Before sending, verify the active conversation surface, chat durability, Project association, model and reasoning or GPT selection, prompt, and attachments.
- Send once, identify the resulting user turn, and bind all later waits, inspections, recovery, and reading to the same tab, chat, turn, and generation. A host wait ending or browser operation timing out is not evidence that the generation ended and does not authorize resending.
- While generation remains active, partial reasoning, answer fragments, and status text are provisional UI state only: their substance SHALL NOT become task evidence, steer the caller's work, or be returned as the result. Inspect them only as needed to establish activity. An enabled same-turn semantic stop, cancel, or interrupt control—or live thinking, searching, tool use, streaming, or continuation state—is affirmative activity and means keep waiting. Identify controls from their current semantic role and state rather than fixed labels, selectors, icons, or coordinates. Never activate an answer-sooner control or send a follow-up, `continue`, correction, or steering prompt while activity remains unless the user explicitly supplied mid-turn instructions.
- After a response, you SHALL NOT request a rewrite, refinement, expansion, reduction, or reorganization merely to make the answer fit your preferred next step. You MAY continue with new or corrected decision-relevant reality, an observably unmet user-set or external interface, or a genuine material question, disagreement, or uncertainty that could change the user's outcome or the correctness of work serving it. Preserve its actual authority and leave the response judgment to ChatGPT.
- Elapsed time, unchanged text or DOM length, repeated status wording, operation timeouts, a substantial-looking fragment, or completed-looking controls establish neither a frozen generation nor completion. Prefer bounded, low-token host waits or a trustworthy same-turn continuation handle; after each resumption, inspect only enough live state to distinguish activity, completion, explicit failure, or ambiguity. Do not impose a short overall deadline or narrate unchanged state.
- Claim natural completion only when a newly identified same-turn response is present and affirmative activity or continuation is unambiguously absent on two checks separated by a settle wait. If activity reappears, keep waiting. A stopped or interrupted state is not natural completion, and absence of activity without positive identification of the new same-turn response is insufficient.
- When a wait or inspection fails, becomes ambiguous, or loses association, dynamically inspect the live UI through safe, reversible, semantically appropriate controls to re-establish the tab, conversation surface, chat, turn, and generation. A reasoning or status disclosure MAY be monitored for evidence of changing activity, but its substance remains provisional. Automatic refresh is a last resort after safer recovery fails, only for a positively identified durable non-temporary chat after protecting refresh-sensitive state; never refresh a temporary chat. After recovery, reverify every bound identity and resume waiting or read the settled final response. Report an explicit visible UI failure when present; otherwise unresolved state is inconclusive rather than frozen or failed.
- Keep ordinary waiting in the host. Do not create page-executed observers, timers, polling, network requests, persisted scripts, DOM mutations, clicks, or event dispatch merely to wait; safe reversible live-UI inspection for ambiguous-state recovery is not a waiting loop.
- Give the complete send/wait/read cycle exclusive use of its tab. Concurrent agents use separate tabs and preferably separate chats, or serialize the cycle. Never coordinate browser ownership through repository files, temporary files, page globals, or shared locks.

### Read the complete response

- After settled completion, read the complete final response, including relevant collapsed or continued content. Waiting without reading is incomplete.
- Do not call a response or code block truncated merely because extracted DOM text ends abruptly. If syntax ends mid-expression, rendered height conflicts with extracted text, or a long region contains lazy or virtualized space, scroll through that region to materialize it and reread overlapping chunks.
- Continue until the relevant region has no unmaterialized content and no continuation control remains. Deduplicate overlaps and verify expected beginnings and endings or syntax before relying on consequential code.
- Prefer scrolling and materialization over a copy control that could overwrite protected clipboard state. Request continuation only after scrolling shows the content absent.
- Verify each requested artifact in the surface that carries its payload. A completed response shell, label, control, or extracted text does not establish that a file, image, diagram, citation, or app result is usable; if applicable processing or materialization still leaves it unavailable, report inconclusive without assigning a cause.
- Return the actual findings to the calling task. Preserve a useful durable chat and return its identity or URL when helpful.
- Extract a temporary-chat result before leaving. Avoid abandoned drafts, pending uploads, and duplicate attachments.
- After extracting a result and resolving its draft, uploads, attachments, dialogs, and generation state, close only a tab whose tracked created identity still resolves unambiguously. Closing it does not delete a durable chat; return the chat identity or URL when that is the retained artifact.
- Treat uncertain or rebound tab identity as pre-existing protected state and do not close it. Keep a verified created tab open only when the user asked for the live page or unresolved state requires a handoff, and make that disposition explicit.
