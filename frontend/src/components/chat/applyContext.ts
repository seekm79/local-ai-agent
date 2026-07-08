import { createContext } from "react";

// When provided (coding mode), assistant code blocks show an "Apply" button
// that hands the raw block text to this callback (opens a diff preview).
export const ApplyContext = createContext<((code: string) => void) | null>(null);
