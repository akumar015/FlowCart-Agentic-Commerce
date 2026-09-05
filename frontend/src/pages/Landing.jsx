import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ShoppingBag,
  Sparkles,
  ShieldCheck,
  Zap,
  Lock,
  MessageSquare,
  CreditCard,
  CheckCircle2,
  ChevronRight,
  Bot
} from 'lucide-react';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#0B0F19] text-slate-100 flex flex-col justify-between selection:bg-indigo-500 selection:text-white">
      {/* Background Subtle Glows */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-indigo-600/15 blur-[120px] rounded-full" />
        <div className="absolute top-1/2 -right-40 w-[500px] h-[350px] bg-violet-600/10 blur-[140px] rounded-full" />
      </div>

      {/* Navbar */}
      <header className="border-b border-slate-800/70 backdrop-blur-md bg-[#0B0F19]/80 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center cursor-pointer select-none" onClick={() => navigate('/')}>
            <span className="font-extrabold text-xl md:text-2xl tracking-tight text-white hover:text-indigo-400 transition-colors">
              FlowCart
            </span>
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/chat')}
              className="text-xs md:text-sm font-semibold px-4 py-2 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white transition-all shadow-sm shadow-indigo-500/20 flex items-center space-x-1.5"
            >
              <span>Shop Now</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="max-w-6xl mx-auto px-6 pt-16 pb-24 flex flex-col items-center relative z-10">
        {/* Badge */}
        <div className="inline-flex items-center space-x-2 px-4 py-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 text-indigo-300 text-xs font-semibold mb-8 backdrop-blur">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <span>Conversational In-App Checkout • Track 01</span>
        </div>

        {/* Hero Title & Subtitle */}
        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-center max-w-4xl leading-[1.12]">
          E-commerce,{' '}
          <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
            Reimagined.
          </span>
        </h1>

        <p className="mt-6 text-lg md:text-xl text-slate-400 text-center max-w-2xl leading-relaxed">
          Say goodbye to complex filter trees and cumbersome checkout flows. Talk naturally with an AI
          cashier that finds products, manages your cart, and secures payments with mandate spending limits.
        </p>

        {/* Hero Actions */}
        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          <button
            onClick={() => navigate('/chat')}
            className="w-full sm:w-auto inline-flex items-center justify-center space-x-2 px-8 py-3.5 rounded-full bg-gradient-to-r from-indigo-500 via-indigo-600 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white font-semibold text-base shadow-xl shadow-indigo-500/30 transition-all transform hover:-translate-y-0.5 active:translate-y-0"
          >
            <span>Start Shopping Now</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          <a
            href="#demo"
            className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3.5 rounded-full border border-slate-700 hover:border-slate-600 bg-slate-900/60 hover:bg-slate-800 text-slate-300 hover:text-white font-medium text-sm transition-all"
          >
            See How It Works
          </a>
        </div>

        {/* Live Conversation Showcase Preview */}
        <div id="demo" className="mt-16 w-full max-w-3xl rounded-2xl border border-slate-800 bg-slate-900/80 p-5 md:p-6 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4 text-xs text-slate-400">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-mono font-medium text-slate-300">Live Agent Graph Simulator</span>
            </div>
            <span className="bg-slate-800 text-slate-400 px-2 py-0.5 rounded text-[11px]">LangGraph + Gemini</span>
          </div>

          <div className="space-y-4 text-sm">
            {/* User message */}
            <div className="flex justify-end">
              <div className="bg-indigo-600 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm max-w-[85%]">
                I need a stylish analog watch for men under ₹1,000. Add it to my cart!
              </div>
            </div>

            {/* AI Agent message */}
            <div className="flex items-start space-x-3">
              <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-indigo-500 to-violet-600 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-sm">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div className="bg-slate-800/90 text-slate-200 border border-slate-700/60 px-4 py-3 rounded-2xl rounded-tl-sm max-w-[88%] space-y-2">
                <p>
                  Found <strong className="text-white">Camerii WM64 Elegance Analog Watch</strong> for{' '}
                  <span className="text-emerald-400 font-semibold">₹449</span>.
                </p>
                <div className="p-2.5 bg-slate-900/90 rounded-xl border border-slate-800 flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>Added to Cart • Total: <strong>₹449</strong></span>
                  </div>
                  <span className="text-emerald-400 font-medium">Under Limit (₹5,000)</span>
                </div>
                <p className="text-xs text-slate-400">
                  Would you like to proceed with checkout, or look for footwear and accessories?
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-20 text-left w-full">
          <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-indigo-500/50 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4 group-hover:scale-105 transition-transform">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Natural Product Discovery</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Real-time semantic search through catalog inventory with automatic stock validation and flavor/size variant resolution.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-violet-500/50 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-violet-500/10 text-violet-400 flex items-center justify-center mb-4 group-hover:scale-105 transition-transform">
              <Lock className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Mandate Spending Gates</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Safety-first architecture. Hardcoded safety nodes intercept payments exceeding pre-set user transaction limits before triggering payment links.
            </p>
          </div>

          <div className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800/80 hover:border-emerald-500/50 transition-all group">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4 group-hover:scale-105 transition-transform">
              <CreditCard className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-white">Razorpay In-Chat Checkout</h3>
            <p className="mt-2 text-sm text-slate-400 leading-relaxed">
              Generate native payment links and verify asynchronously through webhooks without leaving the conversational thread.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-8 px-6 text-center text-xs text-slate-500 relative z-10">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <span>© {new Date().getFullYear()} FlowCart. Agentic Commerce Powered by LangGraph & Gemini.</span>
          <div className="flex items-center space-x-6 text-slate-400">
            <button onClick={() => navigate('/chat')} className="hover:text-indigo-400 transition-colors">
              Chat Interface
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
