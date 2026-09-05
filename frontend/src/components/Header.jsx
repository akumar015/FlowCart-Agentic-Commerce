import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShoppingBag, Terminal, User, ChevronDown, ArrowLeft } from 'lucide-react';

export default function Header({
  showBack = false,
  users = [],
  selectedUserId,
  onSelectUser,
  userProfile = {},
  mandate,
  cartCount = 0,
  activeDrawer,
  onToggleDrawer,
}) {
  const navigate = useNavigate();

  return (
    <header className="h-16 border-b border-slate-800/80 px-4 md:px-6 flex items-center justify-between bg-[#0B0F19]/90 backdrop-blur z-20 sticky top-0">
      {/* Left: Brand / Logo */}
      <div className="flex items-center space-x-3">
        {showBack && (
          <button
            onClick={() => navigate('/')}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors mr-1"
            title="Back to Home"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
        )}

        <div
          onClick={() => navigate('/')}
          className="flex items-center cursor-pointer group select-none"
        >
          <span className="font-extrabold text-xl md:text-2xl tracking-tight text-white group-hover:text-indigo-400 transition-colors">
            FlowCart
          </span>
        </div>
      </div>

      {/* Right: Controls (User, Cart, Dev) */}
      <div className="flex items-center space-x-2.5 md:space-x-3">
        {/* Mandate Status Badge */}
        {mandate && mandate.is_active && (
          <div
            className="hidden sm:flex items-center space-x-1.5 bg-emerald-950/60 border border-emerald-500/30 rounded-full px-3 py-1.5 text-xs text-emerald-300 shadow-sm shadow-emerald-950/50"
            title={`Approved Auto-Debit Categories: ${mandate.allowed_categories?.join(', ') || 'Clothing, Footwear'}`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shrink-0" />
            <span className="font-semibold">UPI Autopay</span>
            <span className="text-emerald-400/80 font-mono text-[11px]">(≤ ₹{mandate.max_amount_per_tx?.toLocaleString('en-IN')})</span>
          </div>
        )}

        {/* User Selector */}
        {users.length > 0 && (
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-full px-3 py-1.5 text-xs text-slate-300 hover:border-slate-700 transition-colors">
            <User className="w-3.5 h-3.5 mr-1.5 text-indigo-400 shrink-0" />
            <select
              value={selectedUserId || ''}
              onChange={(e) => onSelectUser && onSelectUser(Number(e.target.value))}
              className="bg-transparent text-slate-200 focus:outline-none cursor-pointer font-medium pr-1 text-xs max-w-[120px] md:max-w-[180px] truncate"
            >
              {users.map((u) => (
                <option key={u.id} value={u.id} className="bg-slate-900 text-slate-200">
                  {u.name} (₹{u.spend_limit_per_tx ? u.spend_limit_per_tx.toLocaleString('en-IN') : '5,000'})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Cart Drawer Button */}
        <button
          onClick={() => onToggleDrawer && onToggleDrawer('cart')}
          className={`relative p-2.5 rounded-full border transition-all ${
            activeDrawer === 'cart'
              ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
              : 'bg-slate-900 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white'
          }`}
          title="Live Cart"
        >
          <ShoppingBag className="w-4 h-4" />
          {cartCount > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-indigo-500 text-white text-[10px] font-bold flex items-center justify-center shadow-md animate-pulse">
              {cartCount}
            </span>
          )}
        </button>

        {/* Dev Mode & Audit Button */}
        <button
          onClick={() => onToggleDrawer && onToggleDrawer('dev')}
          className={`p-2.5 rounded-full border transition-all ${
            activeDrawer === 'dev'
              ? 'bg-violet-600/20 border-violet-500 text-violet-300'
              : 'bg-slate-900 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white'
          }`}
          title="Dev Mode & Audit Logs"
        >
          <Terminal className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
