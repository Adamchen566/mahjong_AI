import { useEffect, useState } from 'react'
import { setSoundEnabled, setVoiceEnabled, soundEnabled, voiceAvailable, voiceEnabled } from './sound'

/** 声音和报牌的开关。报牌需要音频文件,这个版本没带的话就不显示那个按钮。 */
export function SoundToggles() {
  const [soundOn, setSoundOn] = useState(soundEnabled())
  const [voiceOn, setVoiceOn] = useState(voiceEnabled())
  const [hasVoice, setHasVoice] = useState(false)
  useEffect(() => {
    let alive = true
    void voiceAvailable().then((ok) => alive && setHasVoice(ok))
    return () => {
      alive = false
    }
  }, [])
  return (
    <>
      <button
        className="btn"
        onClick={() => {
          setSoundEnabled(!soundOn)
          setSoundOn(!soundOn)
        }}
        aria-pressed={soundOn}
      >
        声音 {soundOn ? '开' : '关'}
      </button>
      {hasVoice && (
        <button
          className="btn"
          disabled={!soundOn}
          title={soundOn ? '四个座位各有一个声音,打出什么牌就报什么' : '先把声音打开'}
          onClick={() => {
            setVoiceEnabled(!voiceOn)
            setVoiceOn(!voiceOn)
          }}
          aria-pressed={voiceOn && soundOn}
        >
          报牌 {voiceOn && soundOn ? '开' : '关'}
        </button>
      )}
    </>
  )
}

const INSIGHT_KEY = 'mahjong.insight'

/** 牌理(向听数、进张、听牌提示)显示不显示,记在浏览器里。 */
export function useInsightPreference(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(INSIGHT_KEY) !== 'off'
    } catch {
      return true
    }
  })
  const set = (next: boolean) => {
    setOn(next)
    try {
      localStorage.setItem(INSIGHT_KEY, next ? 'on' : 'off')
    } catch {
      // 存不了就只在这次打开期间生效
    }
  }
  return [on, set]
}
