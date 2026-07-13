import type { MouseEventHandler } from 'react'

type Props={ state?:'idle'|'listening'|'planning'|'working'|'waiting'|'ready'; onClick?:MouseEventHandler<HTMLButtonElement>; compact?:boolean }
export function Bird({state='idle',onClick,compact=false}:Props){
  return <button className={`bird bird--${state} ${compact?'bird--compact':''}`} onClick={onClick} aria-label={`Kolibri: ${state}`} data-testid="bird">
    <img src="/kolibri-bird.svg" alt="" draggable={false}/><span className="bird__pulse"/>
  </button>
}
