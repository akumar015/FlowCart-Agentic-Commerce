import React from 'react';
import { ShoppingBag, Terminal, X, ShieldAlert, CheckCircle2, Clock } from 'lucide-react';

export default function Drawer({
  isOpen = false,
  activeView = 'cart', // 'cart' | 'dev'
  onClose,
  onSwitchView,
  cart = { items: [], grandTotal: 0, itemCount: 0 },
  userProfile = {},
  mandate = null,
  sessionId = '',
  auditLogs = [],
}) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop overlay for mobile & focused reading */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30 transition-opacity"
      />

      {/* Drawer panel */}
      <aside className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col transition-all duration-300 ease-in-out">
        {/* Top Header with Tab Switcher */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-1 bg-slate-900 border border-slate-800 p-1 rounded-xl">
            <button
              onClick={() => onSwitchView && onSwitchView('cart')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeView === 'cart'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              <span>Cart ({cart.itemCount})</span>
            </button>

            <button
              onClick={() => onSwitchView && onSwitchView('dev')}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeView === 'dev'
                  ? 'bg-violet-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Dev & Audit</span>
            </button>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Close Drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {activeView === 'cart' ? (
            /* CART VIEW */
            <div className="h-full flex flex-col justify-between space-y-4">
              {cart.items.length === 0 ? (
                <div className="my-auto text-center py-16">
                  <div className="w-14 h-14 rounded-2xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center mx-auto text-slate-500 mb-3 shadow-inner">
                    <ShoppingBag className="w-7 h-7" />
                  </div>
                  <h4 className="text-sm font-semibold text-slate-300">Your cart is empty</h4>
                  <p className="text-xs text-slate-500 mt-1 max-w-[220px] mx-auto leading-relaxed">
                    Ask the conversational agent to find products and add items to your cart.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {cart.items.map((item, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/70 hover:border-slate-600 transition-colors flex items-start justify-between"
                    >
                      <div className="pr-3">
                        <h4 className="text-sm font-semibold text-slate-100">{item.title}</h4>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {item.color ? item.color : ''} {item.size ? `• ${item.size}` : ''}
                        </p>
                        <div className="inline-flex items-center space-x-1 mt-2 text-xs bg-indigo-500/10 text-indigo-300 px-2 py-0.5 rounded font-medium">
                          <span>Qty: {item.quantity}</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="text-sm font-bold text-slate-100">
                          ₹{item.item_total ? item.item_total.toLocaleString('en-IN') : '0'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Cart Financial Summary & Safety Check */}
              <div className="border-t border-slate-800 pt-4 mt-auto space-y-3 bg-slate-900/90">
                <div className="flex justify-between items-center text-xs text-slate-400">
                  <span>Mandate Auto-Pay Cap</span>
                  <span className="text-emerald-400 font-semibold font-mono">
                    ₹{mandate?.max_amount_per_tx ? mandate.max_amount_per_tx.toLocaleString('en-IN') : '4,000'} / tx
                  </span>
                </div>

                <div className="flex justify-between items-center text-base font-bold text-slate-100 pb-1">
                  <span>Grand Total</span>
                  <span className="text-indigo-400 text-xl font-extrabold">
                    ₹{cart.grandTotal ? cart.grandTotal.toLocaleString('en-IN') : '0'}
                  </span>
                </div>

                {/* Mandate Status Pill */}
                {cart.grandTotal > (mandate?.max_amount_per_tx || 4000) ? (
                  <div className="flex items-center space-x-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                    <ShieldAlert className="w-4 h-4 shrink-0 text-amber-400" />
                    <span>Exceeds mandate cap (₹{mandate?.max_amount_per_tx?.toLocaleString('en-IN') || '4,000'}). Gated via Razorpay payment link.</span>
                  </div>
                ) : cart.grandTotal > 0 ? (
                  <div className="flex items-center space-x-2 p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs">
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                    <span>Within mandate cap! Eligible for autonomous zero-click auto-debit.</span>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            /* DEV & AUDIT LOG VIEW */
            <div className="space-y-4">
              {/* Active Mandate Delegation Info */}
              {mandate && (
                <div className="p-3.5 bg-slate-950 border border-emerald-500/30 rounded-xl space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-emerald-400 flex items-center space-x-1">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      <span>{mandate.mandate_type} ({mandate.provider})</span>
                    </span>
                    <span className="text-[10px] text-emerald-500/80 uppercase font-mono">ACTIVE DELEGATION</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] pt-1 border-t border-slate-800">
                    <div>
                      <span className="text-slate-500 block">Max Limit/Tx:</span>
                      <span className="font-mono text-slate-200">₹{mandate.max_amount_per_tx?.toLocaleString('en-IN')}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Token ID:</span>
                      <span className="font-mono text-slate-300 truncate block">{mandate.razorpay_token_id || 'Mock_Token'}</span>
                    </div>
                  </div>
                  <div className="text-[11px] pt-1">
                    <span className="text-slate-500 block">Approved Categories:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {mandate.allowed_categories?.map((cat, i) => (
                        <span key={i} className="px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-500/30 text-[10px] text-emerald-300">
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1 text-xs">
                <span className="text-slate-400 block font-medium">Active Session:</span>
                <code className="text-[11px] text-indigo-300 break-all font-mono">
                  {sessionId || 'N/A'}
                </code>
              </div>

              <div className="border-t border-slate-800 pt-3">
                <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-3">
                  Safety Gate & Agent Audit Trail
                </h4>

                {auditLogs.length === 0 ? (
                  <div className="text-center py-10 text-slate-500 text-xs italic">
                    <Clock className="w-5 h-5 mx-auto mb-2 opacity-50" />
                    No audit records logged yet. Interact with the chat to see decisions streamed here.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {auditLogs.map((log, index) => (
                      <div
                        key={index}
                        className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 text-xs font-mono space-y-1.5"
                      >
                        <div className="flex items-center justify-between text-[10px]">
                          <span className="text-slate-500">{log.timestamp ? log.timestamp.slice(11, 19) : 'Now'}</span>
                          <span
                            className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${
                              log.action_type?.includes('PAYMENT')
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                                : log.action_type?.includes('GATE') || log.is_gated
                                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                                : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30'
                            }`}
                          >
                            {log.action_type || 'SAFE_TOOL'}
                          </span>
                        </div>
                        <p className="text-slate-200 text-xs leading-relaxed font-sans">{log.reasoning || log.action_type}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
