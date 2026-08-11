# Garden of Jihan UI Vision

The original Garden of Jihan previews shown during concept development are the visual target for the production application, not discarded mockups.

During the first runnable engineering build, some of the original visual depth was intentionally simplified while the local backend, security boundary, Windows packaging, and analysis pipeline were stabilized. The production UI should now move back toward the original concept without sacrificing performance or accessibility.

## Visual language to preserve

- Light, airy interface rather than a dark dashboard.
- `جيهان` mark beside the Garden of Jihan name.
- Large, varied flowerbeds and a sense of a broad garden landscape behind the workspace.
- Soft hills, sunlight, atmospheric depth, and translucent glass-like working panels.
- Mixed flower colors rather than a single accent color.
- Slow whole flowers drifting downward while gently swaying in a breeze.
- Subtle parallax as the user scrolls.
- Calm motion during normal use, with motion reduced during heavy analysis and when the operating system requests reduced motion.
- Clear six-step workflow that stays easier to use than a professional video editor.

## Production principle

The garden should feel alive without competing with the task. Decorative animation must remain behind the controls, avoid blocking clicks, scale down on smaller screens, and respect `prefers-reduced-motion`.

The current vector design target is [`design-preview.svg`](design-preview.svg). Future UI changes should be compared against this vision before release.
