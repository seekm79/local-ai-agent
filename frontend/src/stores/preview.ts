import { create } from "zustand";

// A global preview surface available in every mode. Any component can call
// usePreview.getState().open(...) to show HTML, a dev-server URL, an image, or
// a video in a modal.
export type PreviewContent =
  | { kind: "html"; html: string; title?: string }
  | { kind: "url"; url: string; title?: string }
  | { kind: "image"; src: string; title?: string }
  | { kind: "video"; src: string; title?: string }
  | { kind: "diff"; path: string; before: string; after: string; title?: string };

interface PreviewState {
  content: PreviewContent | null;
  open: (c: PreviewContent) => void;
  close: () => void;
}

export const usePreview = create<PreviewState>((set) => ({
  content: null,
  open: (content) => set({ content }),
  close: () => set({ content: null }),
}));
