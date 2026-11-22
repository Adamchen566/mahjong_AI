import { useCallback, useEffect, useRef, useState } from 'react'
import { playAlert, playEnd, playEvent } from './sound'
import { calloutOf, describeEvent, type LogLine } from './tiles'
import type { MatchInfo, StateMessage, View } from './types'

export interface Callout {
  id: number
  seat: number
  text: string
}

export interface LoggedLine extends LogLine {
  id: number
}

/** 和本地服务保持一条 WebSocket 连接,把收到的局面、记录和喊话交给界面。 */
export function useGame() {
  const [connected, setConnected] = useState(false)
  const [ready, setReady] = useState(false) // 收到过第一条状态
  const [match, setMatch] = useState<MatchInfo | null>(null)
  const [view, setView] = useState<View | null>(null)
  const [log, setLog] = useState<LoggedLine[]>([])
  const [callouts, setCallouts] = useState<Callout[]>([])
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const nextId = useRef(1)

  useEffect(() => {
    let stopped = false
    let retry: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!stopped) retry = window.setTimeout(connect, 1500)
      }
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'error') {
          setError(msg.message)
          return
        }
        const state = msg as StateMessage
        setReady(true)
        setMatch(state.match)
        setView(state.view)
        if (!state.match) {
          setLog([])
          return
        }
        const me = state.match.human_seat
        const fresh: LoggedLine[] = []
        const shouts: Callout[] = []
        let reset = false
        let soundAt = 0 // 同一条消息里的多个事件依次出声,不叠在一起
        for (const ev of state.events) {
          if (ev.type === 'deal') {
            reset = true
            fresh.length = 0
          }
          soundAt += playEvent(ev, me, soundAt)
          if (ev.type === 'end' && state.view) playEnd(state.view.scores[me], soundAt + 0.2)
          const line = describeEvent(ev, me, state.view)
          if (line) fresh.push({ ...line, id: nextId.current++ })
          const shout = calloutOf(ev)
          if (shout) shouts.push({ ...shout, id: nextId.current++ })
        }
        // 别人打出的牌你可以碰、杠、胡时提醒一声
        const v = state.view
        if (state.events.length && v && v.legal.length && (v.phase === 'RESPONSE' || v.phase === 'ROB_KONG')) {
          playAlert(soundAt + 0.05)
        }
        if (reset || fresh.length) setLog((old) => (reset ? fresh : [...old, ...fresh]))
        if (shouts.length) {
          setCallouts((old) => [...old, ...shouts])
          const ids = new Set(shouts.map((s) => s.id))
          window.setTimeout(() => setCallouts((old) => old.filter((c) => !ids.has(c.id))), 1500)
        }
      }
    }

    connect()
    return () => {
      stopped = true
      window.clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [])

  const send = useCallback((msg: object) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      setError(null)
      ws.send(JSON.stringify(msg))
    }
  }, [])

  const newMatch = useCallback((opponent: string) => send({ type: 'new_match', opponent }), [send])
  const act = useCallback((id: number) => send({ type: 'action', id }), [send])
  const actMany = useCallback((ids: number[]) => send({ type: 'actions', ids }), [send])
  const nextGame = useCallback(() => send({ type: 'next_game' }), [send])
  const quitMatch = useCallback(() => send({ type: 'quit_match' }), [send])
  const setHint = useCallback((on: boolean) => send({ type: 'hint', on }), [send])

  return { connected, ready, match, view, log, callouts, error, newMatch, act, actMany, nextGame, quitMatch, setHint }
}
