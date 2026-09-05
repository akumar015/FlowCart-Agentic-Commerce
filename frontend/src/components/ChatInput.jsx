import React from 'react';
import { Send, Sparkles } from 'lucide-react';

const DEFAULT_SUGGESTIONS = [
  'Show watches for men',
  'Show footwear under ₹1,000',
  "Find women's clothing",
  'What is in my cart?',
  'Checkout my order',
];

export default function ChatInput({
  inputValue,
  onChange,
  onSend,
  isLoading,
  showSuggestions = false,
  onSelectSuggestion,
  suggestions = DEFAULT_SUGGESTIONS,
}) {
  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!inputValue.trim() || isLoading) return;
    onSend && onSend();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-4 md:p-6 bg-gradient-to-t from-[#0B0F19] via-[#0B0F19]/95 to-transparent">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* Suggestion Chips */}
        {showSuggestions && (
          <div className="flex flex-wrap items-center gap-2 pb-1 text-xs">
            <span className="text-slate-400 flex items-center shrink-0 mr-1 font-medium">
              <Sparkles className="w-3.5 h-3.5 mr-1 text-indigo-400" />
              Suggested:
            </span>
            {suggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => onSelectSuggestion && onSelectSuggestion(suggestion)}
                className="px-3.5 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 hover:border-indigo-500/60 hover:bg-indigo-600/10 text-slate-300 hover:text-white transition-all shadow-sm"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {/* Input Bar */}
        <form
          onSubmit={handleSubmit}
          className="relative flex items-center bg-slate-900/90 border border-slate-800 focus-within:border-indigo-500/80 rounded-2xl shadow-xl shadow-black/40 backdrop-blur-md px-4 py-2.5 transition-all"
        >
          <input
            type="text"
            value={inputValue}
            onChange={(e) => onChange && onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about products, add to cart, or checkout..."
            className="flex-1 bg-transparent text-sm md:text-base text-slate-100 placeholder-slate-500 focus:outline-none pr-3"
            autoFocus
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isLoading}
            className="p-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:hover:bg-indigo-600 transition-colors shadow-sm cursor-pointer"
            title="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>

        <div className="text-center text-[11px] text-slate-600">
          FlowCart Agent uses mandate spending gates for safe in-app transactions.
        </div>
      </div>
    </div>
  );
}
