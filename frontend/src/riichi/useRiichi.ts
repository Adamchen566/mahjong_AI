import { useCallback, useEffect, useRef, useState } from 'react'
import { playAlert, playEnd, playRiichiEvent } from '../sound'
import { calloutOf, describeEvent, type RLogLine } from './tiles'
import type { RMatchInfo, RStateMessage, RView } from './types'

export interface RCallout {
  id: number
  seat: number
  text: string
}

export interface RLogged extends RLogLine {
  id: number
}

/** 和本地服务的 /ws/riichi 保持一条连接,断线自动重连。 */
export function useRiichi() {
  const [connected, setConnected] = useState(false)
  const [ready, setReady] = useState(false)
  const [match, setMatch] = useState<RMatchInfo | null>(null)
  const [view, setView] = useState<RView | null>(null)
  const [log, setLog] = useState<RLogged[]>([])
  const [callouts, setCallouts] = useState<RCallout[]>([])
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const nextId = useRef(1)

  useEffect(() => {
    let stopped = false
    let retry: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/riichi`)
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
        const state = msg as RStateMessage
        setReady(true)
        setMatch(state.match)
        setView(state.view)
        if (!state.match) {
          setLog([])
          return
        }
        const me = state.match.human_seat
        const fresh: RLogged[] = []
        const shouts: RCallout[] = []
        let reset = false
        let soundAt = 0 // 同一条消息里的多个事件依次出声,不叠在一起
        for (const ev of state.events) {
          if (ev.type === 'hand_start') {
            reset = true
            fresh.length = 0
          }
          soundAt += playRiichiEvent(ev, me, soundAt)
          if (ev.type === 'game_end' && state.view?.final) playEnd(state.view.final.final_points[me], soundAt + 0.2)
          const line = describeEvent(ev, me)
          if (line) fresh.push({ ...line, id: nextId.current++ })
          const shout = calloutOf(ev)
          if (shout) shouts.push({ ...shout, id: nextId.current++ })
        }
        // 别人打出的牌你可以吃碰杠和时提醒一声
        const v = state.view
        if (state.events.length && v && v.legal.length && (v.phase === 'RESPONSE' || v.phase === 'ROB_KAN')) {
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
  const resume = useCallback(() => send({ type: 'continue' }), [send])
  const quitMatch = useCallback(() => send({ type: 'quit_match' }), [send])
  const setHint = useCallback((on: boolean) => send({ type: 'hint', on }), [send])

  return { connected, ready, match, view, log, callouts, error, newMatch, act, resume, quitMatch, setHint }
}
