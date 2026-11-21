// 声音全部用 Web Audio 现场合成,不带任何音频文件。
// 浏览器规定必须先有一次点击或按键才能出声,所以第一次操作之前是静音的。

import type { GameEvent } from './types'

const STORAGE_KEY = 'mahjong.sound'

let ctx: AudioContext | null = null
let master: GainNode | null = null
let noise: AudioBuffer | null = null
let enabled = readPreference()

function readPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'off'
  } catch {
    return true
  }
}

export function soundEnabled(): boolean {
  return enabled
}

export function setSoundEnabled(on: boolean): void {
  enabled = on
  try {
    localStorage.setItem(STORAGE_KEY, on ? 'on' : 'off')
  } catch {
    // 存不了就只在这次打开期间生效
  }
  if (on) {
    unlock()
    tick(0, 1.4, 0.3) // 打开时响一下,让人知道是什么音量
  }
}

/** 在用户的点击或按键里调用: 建立(或恢复)音频输出。 */
function unlock(): void {
  if (!enabled) return
  if (!ctx) {
    const AC =
      window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AC) return
    ctx = new AC()
    master = ctx.createGain()
    master.gain.value = 0.7
    master.connect(ctx.destination)
    // 一小段白噪声,所有"牌碰桌面"的声音都从它滤出来
    noise = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.2), ctx.sampleRate)
    const data = noise.getChannelData(0)
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  }
  if (ctx.state === 'suspended') void ctx.resume()
}

if (typeof window !== 'undefined') {
  window.addEventListener('pointerdown', unlock)
  window.addEventListener('keydown', unlock)
}

function ready(): { ctx: AudioContext; out: GainNode; noise: AudioBuffer } | null {
  if (!enabled || !ctx || !master || !noise || ctx.state !== 'running') return null
  return { ctx, out: master, noise }
}

// ---------------------------------------------------------------- 基本音色

/** 一张牌拍在桌上: 一小段带通噪声加一点低频的"实"感。 */
function clack(at: number, pitch = 1, gain = 0.5): void {
  const a = ready()
  if (!a) return
  const t = a.ctx.currentTime + at

  const src = a.ctx.createBufferSource()
  src.buffer = a.noise
  const band = a.ctx.createBiquadFilter()
  band.type = 'bandpass'
  band.frequency.value = 1900 * pitch
  band.Q.value = 1.1
  const env = a.ctx.createGain()
  env.gain.setValueAtTime(0.0001, t)
  env.gain.exponentialRampToValueAtTime(gain, t + 0.003)
  env.gain.exponentialRampToValueAtTime(0.0001, t + 0.075)
  src.connect(band).connect(env).connect(a.out)
  src.start(t)
  src.stop(t + 0.1)

  const body = a.ctx.createOscillator()
  body.type = 'sine'
  body.frequency.setValueAtTime(240 * pitch, t)
  body.frequency.exponentialRampToValueAtTime(120 * pitch, t + 0.06)
  const bodyEnv = a.ctx.createGain()
  bodyEnv.gain.setValueAtTime(gain * 0.5, t)
  bodyEnv.gain.exponentialRampToValueAtTime(0.0001, t + 0.07)
  body.connect(bodyEnv).connect(a.out)
  body.start(t)
  body.stop(t + 0.09)
}

/** 轻轻的一声,摸牌用。 */
function tick(at: number, pitch = 1.5, gain = 0.22): void {
  clack(at, pitch, gain)
}

/** 一个带余音的音符。 */
function note(at: number, freq: number, gain = 0.18, length = 0.6, type: OscillatorType = 'triangle'): void {
  const a = ready()
  if (!a) return
  const t = a.ctx.currentTime + at
  const osc = a.ctx.createOscillator()
  osc.type = type
  osc.frequency.value = freq
  const env = a.ctx.createGain()
  env.gain.setValueAtTime(0.0001, t)
  env.gain.exponentialRampToValueAtTime(gain, t + 0.008)
  env.gain.exponentialRampToValueAtTime(0.0001, t + length)
  osc.connect(env).connect(a.out)
  osc.start(t)
  osc.stop(t + length + 0.05)
}

// ---------------------------------------------------------------- 牌局里的声音

/** 根据一条牌局事件出声。返回这段声音大约占多久(秒),调用方据此把连续的事件错开。 */
export function playEvent(ev: GameEvent, me: number, at = 0): number {
  const mine = ev.seat === me
  switch (ev.type) {
    case 'deal': // 洗牌发牌: 一串零碎的碰撞声
      for (let i = 0; i < 9; i++) tick(at + i * 0.05, 1 + ((i * 7) % 5) * 0.12, 0.16)
      return 0.5
    case 'draw':
      if (!mine) return 0
      tick(at)
      return 0.06
    case 'discard':
      clack(at, mine ? 1 : 0.86, mine ? 0.55 : 0.4)
      return 0.12
    case 'pong':
      clack(at, 0.95)
      clack(at + 0.11, 0.9)
      return 0.28
    case 'gang':
      clack(at, 0.9)
      clack(at + 0.1, 0.85)
      clack(at + 0.2, 0.75, 0.6)
      return 0.38
    case 'hu':
      if (mine) {
        ;[523.25, 659.25, 783.99, 1046.5].forEach((f, i) => note(at + i * 0.09, f, 0.2, 0.8))
        return 0.7
      }
      note(at, 659.25, 0.14, 0.5)
      note(at + 0.1, 880, 0.14, 0.6)
      return 0.4
    default:
      return 0
  }
}

/** 一局结束: 赢了上行,输了下行,平了一声。 */
export function playEnd(score: number, at = 0): void {
  if (score > 0) [392, 493.88, 587.33, 783.99].forEach((f, i) => note(at + i * 0.12, f, 0.16, 0.9))
  else if (score < 0) [392, 329.63, 261.63].forEach((f, i) => note(at + i * 0.16, f, 0.14, 0.9, 'sine'))
  else note(at, 440, 0.12, 0.7, 'sine')
}

/** 轮到你决定要不要碰、杠、胡: 两声短促的提醒。 */
export function playAlert(at = 0): void {
  note(at, 880, 0.12, 0.16, 'sine')
  note(at + 0.09, 1174.66, 0.12, 0.22, 'sine')
}
