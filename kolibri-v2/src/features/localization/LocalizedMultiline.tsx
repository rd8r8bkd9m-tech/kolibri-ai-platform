import { Fragment } from 'react'

export function LocalizedMultiline({ text }: { text: string }) {
  return text.split('\n').map((line, index) => (
    <Fragment key={`${index}-${line}`}>
      {index > 0 && <br />}
      {line}
    </Fragment>
  ))
}
