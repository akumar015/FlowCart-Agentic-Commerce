import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '../components/Header';
import Drawer from '../components/Drawer';
import MessageFeed from '../components/MessageFeed';
import ChatInput from '../components/ChatInput';

export default function Chat() {
  const navigate = useNavigate();

  // State
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // User & Session state
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [userProfile, setUserProfile] = useState({});
  const [mandate, setMandate] = useState(null);
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [paymentStatus, setPaymentStatus] = useState('none');
  const [auditLogs, setAuditLogs] = useState([]);
  const [cart, setCart] = useState({ items: [], grandTotal: 0, itemCount: 0 });
  const [upsellItems, setUpsellItems] = useState([]);

  // Drawers: null | 'cart' | 'dev'
  const [activeDrawer, setActiveDrawer] = useState(null);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const [suggestions, setSuggestions] = useState([]);

  // Fetch initial users list and inventory suggestions
  useEffect(() => {
    fetch('http://localhost:8000/api/users')
      .then((res) => res.json())
      .then((data) => {
        if (data.users && data.users.length > 0) {
          setUsers(data.users);
          setSelectedUserId(data.users[0].id);
        }
      })
      .catch((err) => console.error('API not reachable:', err));

    fetch('http://localhost:8000/api/suggestions')
      .then((res) => res.json())
      .then((data) => {
        if (data.suggestions) {
          setSuggestions(data.suggestions);
        }
      })
      .catch((err) => console.error('Error fetching suggestions:', err));
  }, []);

  // When selected user changes, reset session and greet
  useEffect(() => {
    if (!selectedUserId) return;

    const newSessionId = crypto.randomUUID();
    setSessionId(newSessionId);
    setPaymentStatus('none');
    setAuditLogs([]);

    // Fetch user profile
    fetch(`http://localhost:8000/api/users/${selectedUserId}`)
      .then((res) => res.json())
      .then((data) => {
        setUserProfile(data.profile || {});
        setMandate(data.mandate || null);
        // Initial greeting
        const userName = data.profile?.name || 'there';
        setMessages([
          {
            role: 'assistant',
            content: `Hello ${userName}! 👋 I'm your FlowCart shopping assistant. How can I help you today? You can search for products, compare specs, modify your cart, or proceed directly to checkout.`,
          },
        ]);
      })
      .catch((err) => console.error(err));

    fetchCart(newSessionId);
  }, [selectedUserId]);

  const fetchCart = async (sid = sessionId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/cart/${sid}`);
      const data = await res.json();
      if (data.cart) {
        setCart({
          items: data.cart.items || [],
          grandTotal: data.cart.grand_total || 0,
          itemCount: data.cart.total_items_count || 0,
        });
      }
    } catch (e) {
      console.error('Error fetching cart:', e);
    }
  };

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const text = inputValue.trim();
    const userMessage = { role: 'user', content: text };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUserId,
          session_id: sessionId,
          message: text,
          payment_status: paymentStatus,
        }),
      });

      if (!res.ok) throw new Error('API request failed');

      const data = await res.json();
      const msgIndex = (prev => prev.length)([...messages, { role: 'user', content: text }]);
      // Attach upsell items directly to the message for per-message rendering
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          upsellItems: data.upsell_items || [],
        },
      ]);
      setPaymentStatus(data.payment_status);
      if (data.audit_logs) setAuditLogs(data.audit_logs);
      if (data.upsell_items?.length) setUpsellItems(data.upsell_items);
      else setUpsellItems([]);

      // Refresh cart
      fetchCart(sessionId);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ I encountered an error connecting to the backend. Please ensure the Python API server is running on port 8000.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // One-click upsell add handler
  const handleUpsellAdd = async (item) => {
    setIsLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: selectedUserId,
          session_id: sessionId,
          message: `Add variant_id ${item.variant_id} to my cart (${item.title})`,
          payment_status: paymentStatus,
        }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: `➕ Add ${item.title} to cart` },
        { role: 'assistant', content: data.reply, upsellItems: data.upsell_items || [] },
      ]);
      if (data.upsell_items?.length) setUpsellItems(data.upsell_items);
      else setUpsellItems([]);
      fetchCart(sessionId);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#0B0F19] text-slate-100 overflow-hidden font-sans antialiased">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full relative">
        {/* Top Navbar */}
        <Header
          showBack={true}
          users={users}
          selectedUserId={selectedUserId}
          onSelectUser={setSelectedUserId}
          userProfile={userProfile}
          mandate={mandate}
          cartCount={cart.itemCount}
          activeDrawer={activeDrawer}
          onToggleDrawer={(type) => setActiveDrawer(activeDrawer === type ? null : type)}
        />

        {/* Message Feed (ChatGPT / Gemini style center layout) */}
        <MessageFeed
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
          onUpsellAdd={handleUpsellAdd}
        />

        {/* Floating Input Area with Quick Suggestions */}
        <ChatInput
          inputValue={inputValue}
          onChange={setInputValue}
          onSend={handleSendMessage}
          isLoading={isLoading}
          showSuggestions={messages.length <= 2}
          suggestions={suggestions.length > 0 ? suggestions : undefined}
          onSelectSuggestion={(s) => {
            setInputValue(s);
          }}
        />
      </div>

      {/* Slide-out Drawer (Cart & Dev Mode) */}
      <Drawer
        isOpen={Boolean(activeDrawer)}
        activeView={activeDrawer || 'cart'}
        onClose={() => setActiveDrawer(null)}
        onSwitchView={(view) => setActiveDrawer(view)}
        cart={cart}
        userProfile={userProfile}
        mandate={mandate}
        sessionId={sessionId}
        auditLogs={auditLogs}
      />
    </div>
  );
}
