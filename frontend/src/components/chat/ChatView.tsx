import { useEffect } from "react";
import { useSession } from "../../stores/session";
import ChatSidebar from "./ChatSidebar";
import MessageList from "./MessageList";
import Composer from "./Composer";

export default function ChatView() {
  const { loadChats, error, clearError } = useSession();

  useEffect(() => {
    void loadChats();
  }, [loadChats]);

  return (
    <div className="flex h-full min-h-0">
      <ChatSidebar />
      <div className="flex min-h-0 flex-1 flex-col">
        {error && (
          <div className="flex items-center justify-between bg-red-950/60 px-4 py-2 text-sm text-red-200">
            <span>{error}</span>
            <button className="hover:text-white" onClick={clearError}>
              dismiss
            </button>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <div className="mx-auto max-w-3xl">
            <MessageList />
          </div>
        </div>
        <div className="mx-auto w-full max-w-3xl">
          <Composer />
        </div>
      </div>
    </div>
  );
}
