'use client'

import { useState } from 'react'
import { MessageSquare, Users, Target, Shield, Activity, BarChart3 } from 'lucide-react'

interface AgentMessage {
  role: 'user' | 'agent'
  content: string
  handler?: string
  compliance?: { pass: boolean; note: string }
}

export default function Home() {
  const [messages, setMessages] = useState<AgentMessage[]>([
    {
      role: 'agent',
      content: 'Welcome to TurnRiverSDR. I\'m your governed AI Sales Development agent. How can I help you today?\n\nI can assist with:\n• Defining ICPs and target segments\n• Researching prospects and companies\n• Qualifying leads against your criteria\n• Drafting outreach sequences\n• Staging enrollments (with approval)\n\nWhat would you like to work on?',
      handler: 'pal-intake',
      compliance: { pass: true, note: 'No side-effect requested' }
    }
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const handleSend = async () => {
    if (!input.trim()) return

    const userMessage: AgentMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // Simulate agent response (in production, call Bedrock AgentCore API)
    setTimeout(() => {
      const agentResponse: AgentMessage = {
        role: 'agent',
        content: `I've received your request: "${input}"\n\nI'll route this to the appropriate specialist agent and provide you with a structured response. This is a dry-run preview - no external actions will be taken without your explicit approval.\n\nWould you like me to proceed with research, or do you have additional constraints to specify?`,
        handler: 'npao-orchestrator',
        compliance: { pass: false, note: 'BLOCKED: external action requires human approval; preview only' }
      }
      setMessages(prev => [...prev, agentResponse])
      setIsLoading(false)
    }, 1500)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-teal-700 rounded-lg flex items-center justify-center">
              <Target className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-slate-900">TurnRiverSDR</h1>
              <p className="text-sm text-slate-500">AI Sales Development Agent</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-100 text-green-800 rounded-full text-sm">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              Live Bedrock
            </div>
            <Shield className="w-5 h-5 text-teal-700" />
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto p-6 grid grid-cols-12 gap-6">
        {/* Sidebar */}
        <div className="col-span-3 space-y-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Activity className="w-4 h-4" />
              Workspace
            </h3>
            <div className="space-y-3">
              <div className="p-3 bg-slate-50 rounded-lg">
                <p className="text-sm font-medium text-slate-700">TurnRiver Portfolio</p>
                <p className="text-xs text-slate-500 mt-1">Multi-tenant enabled</p>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-600">Active ICPs</span>
                <span className="font-semibold text-teal-700">7</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-600">Staged Prospects</span>
                <span className="font-semibold text-teal-700">42</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-600">Pending Approval</span>
                <span className="font-semibold text-amber-600">3</span>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4" />
              Compliance
            </h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-green-700">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                No-Auto-Send
              </div>
              <div className="flex items-center gap-2 text-sm text-green-700">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                Approval Gates
              </div>
              <div className="flex items-center gap-2 text-sm text-green-700">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                Audit Trail
              </div>
              <div className="flex items-center gap-2 text-sm text-green-700">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                Suppression Ready
              </div>
            </div>
          </div>

          <div className="bg-teal-50 rounded-xl border border-teal-200 p-4">
            <h3 className="font-semibold text-teal-900 mb-2">AWS Well-Architected</h3>
            <p className="text-sm text-teal-700 mb-3">Reviewed across 6 pillars with 10 priority recommendations implemented.</p>
            <a 
              href="/wafr-review" 
              className="text-sm font-medium text-teal-800 hover:text-teal-900 underline"
            >
              View WAFR Report →
            </a>
          </div>
        </div>

        {/* Main Chat */}
        <div className="col-span-9">
          <div className="bg-white rounded-xl border border-slate-200 h-[calc(100vh-200px)] flex flex-col">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-5 py-4 ${
                    msg.role === 'user' 
                      ? 'bg-teal-700 text-white' 
                      : 'bg-slate-100 text-slate-900'
                  }`}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.handler && (
                      <div className={`mt-3 pt-3 border-t ${
                        msg.role === 'user' ? 'border-teal-600' : 'border-slate-200'
                      }`}>
                        <div className="flex items-center gap-2 text-xs opacity-75">
                          <span>Handler: {msg.handler}</span>
                          {msg.compliance && (
                            <span className={`px-2 py-0.5 rounded ${
                              msg.compliance.pass 
                                ? 'bg-green-500/20 text-green-100' 
                                : 'bg-amber-500/20 text-amber-100'
                            }`}>
                              {msg.compliance.pass ? '✓ Compliant' : '⚠ Approval Required'}
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-slate-100 rounded-2xl px-5 py-4 flex items-center gap-2">
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce delay-100" />
                    <div className="w-2 h-2 bg-slate-400 rounded-full animate-bounce delay-200" />
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="border-t border-slate-200 p-4">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                  placeholder="Ask about ICPs, research prospects, draft sequences..."
                  className="flex-1 px-4 py-3 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
                <button
                  onClick={handleSend}
                  disabled={isLoading || !input.trim()}
                  className="px-6 py-3 bg-teal-700 text-white rounded-lg font-medium hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <MessageSquare className="w-4 h-4" />
                  Send
                </button>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                No external actions without approval. All requests are dry-run previews until explicitly approved.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-sm text-slate-500">
          <div>TurnRiverSDR © 2026 — Built on AWS Well-Architected Framework</div>
          <div className="flex items-center gap-4">
            <span>Region: us-east-1</span>
            <span>Model: amazon.nova-pro-v1:0</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
