import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(__dirname, '../public/mascot')
const outFile = resolve(outDir, 'kolibri-cartoon.json')
const manifestFile = resolve(outDir, 'manifest.json')

const FR = 24
const SEGMENT = 60
const TOTAL = SEGMENT * 6

const rgba = (hex, alpha = 1) => {
  const clean = hex.replace('#', '')
  const value = Number.parseInt(clean, 16)
  return [
    ((value >> 16) & 255) / 255,
    ((value >> 8) & 255) / 255,
    (value & 255) / 255,
    alpha,
  ]
}

const ease = {
  i: { x: [0.55], y: [1] },
  o: { x: [0.45], y: [0] },
}

const hold = (t, s) => ({ t, s, h: 1 })
const frame = (t, s, e) => ({ ...ease, t, s, e })

const prop = (k, ix) => ({ a: 0, k, ix })
const anim = (k, ix) => ({ a: 1, k, ix })

const transform = ({
  anchor = [0, 0, 0],
  position = [0, 0, 0],
  scale = [100, 100, 100],
  rotate = 0,
  opacity = 100,
}) => ({
  o: Array.isArray(opacity[0]) || typeof opacity[0] === 'object' ? anim(opacity, 11) : prop(opacity, 11),
  r: Array.isArray(rotate[0]) || typeof rotate[0] === 'object' ? anim(rotate, 10) : prop(rotate, 10),
  p: Array.isArray(position[0]) || typeof position[0] === 'object' ? anim(position, 2) : prop(position, 2),
  a: prop(anchor, 1),
  s: Array.isArray(scale[0]) || typeof scale[0] === 'object' ? anim(scale, 6) : prop(scale, 6),
})

const ellipse = (name, size, pos = [0, 0]) => ({
  ty: 'el',
  nm: name,
  p: prop(pos, 3),
  s: prop(size, 2),
  d: 1,
})

const fill = (color, opacity = 100) => ({
  ty: 'fl',
  nm: 'fill',
  c: prop(color, 4),
  o: prop(opacity, 5),
  r: 1,
})

const stroke = (color, width, opacity = 100) => ({
  ty: 'st',
  nm: 'stroke',
  c: prop(color, 3),
  o: prop(opacity, 4),
  w: prop(width, 5),
  lc: 2,
  lj: 2,
  ml: 4,
  bm: 0,
})

const path = (name, v, i, o, closed = true) => ({
  ty: 'sh',
  nm: name,
  ks: {
    a: 0,
    k: { i, o, v, c: closed },
    ix: 2,
  },
})

const group = (name, items) => ({
  ty: 'gr',
  nm: name,
  it: [
    ...items,
    {
      ty: 'tr',
      nm: 'Transform',
      p: prop([0, 0], 2),
      a: prop([0, 0], 1),
      s: prop([100, 100], 3),
      r: prop(0, 6),
      o: prop(100, 7),
      sk: prop(0, 4),
      sa: prop(0, 5),
    },
  ],
})

let ind = 1

const baseLayer = (name, parent, shapes, ks, extra = {}) => ({
  ddd: 0,
  ind: ind++,
  ty: 4,
  nm: name,
  parent,
  sr: 1,
  ks,
  ao: 0,
  shapes,
  ip: 0,
  op: TOTAL,
  st: 0,
  bm: 0,
  ...extra,
})

const nullLayer = (name, ks) => ({
  ddd: 0,
  ind: ind++,
  ty: 3,
  nm: name,
  sr: 1,
  ks,
  ao: 0,
  ip: 0,
  op: TOTAL,
  st: 0,
  bm: 0,
})

const opacityWindow = (start, end, pulse = false) => {
  if (!pulse) {
    return [
      hold(0, [0]),
      hold(Math.max(0, start - 1), [0]),
      hold(start, [100]),
      hold(end, [100]),
      hold(Math.min(TOTAL, end + 1), [0]),
      hold(TOTAL, [0]),
    ]
  }
  return [
    hold(0, [0]),
    hold(Math.max(0, start - 1), [0]),
    frame(start, [0], [100]),
    frame(start + 10, [100], [45]),
    frame(start + 20, [45], [100]),
    frame(start + 36, [100], [30]),
    frame(end, [30], [0]),
    hold(Math.min(TOTAL, end + 1), [0]),
  ]
}

const rootPosition = [
  frame(0, [256, 258, 0], [256, 247, 0]),
  frame(14, [256, 247, 0], [259, 260, 0]),
  frame(30, [259, 260, 0], [253, 251, 0]),
  frame(45, [253, 251, 0], [256, 258, 0]),
  frame(60, [256, 252, 0], [256, 244, 0]),
  frame(74, [256, 244, 0], [256, 253, 0]),
  frame(88, [256, 253, 0], [257, 246, 0]),
  frame(104, [257, 246, 0], [256, 252, 0]),
  frame(120, [256, 250, 0], [263, 245, 0]),
  frame(128, [263, 245, 0], [250, 255, 0]),
  frame(136, [250, 255, 0], [262, 247, 0]),
  frame(144, [262, 247, 0], [251, 253, 0]),
  frame(152, [251, 253, 0], [260, 246, 0]),
  frame(164, [260, 246, 0], [256, 250, 0]),
  frame(180, [256, 256, 0], [256, 227, 0]),
  frame(190, [256, 227, 0], [256, 260, 0]),
  frame(205, [256, 260, 0], [256, 242, 0]),
  frame(222, [256, 242, 0], [256, 252, 0]),
  frame(240, [256, 252, 0], [247, 252, 0]),
  frame(246, [247, 252, 0], [266, 252, 0]),
  frame(252, [266, 252, 0], [249, 253, 0]),
  frame(258, [249, 253, 0], [264, 251, 0]),
  frame(264, [264, 251, 0], [252, 252, 0]),
  frame(274, [252, 252, 0], [259, 252, 0]),
  frame(286, [259, 252, 0], [256, 252, 0]),
  frame(300, [256, 267, 0], [256, 272, 0]),
  frame(330, [256, 272, 0], [256, 267, 0]),
  frame(360, [256, 267, 0], [256, 267, 0]),
]

const rootRotation = [
  frame(0, [-2], [2]),
  frame(28, [2], [-1]),
  frame(60, [0], [4]),
  frame(90, [4], [0]),
  frame(120, [-5], [5]),
  frame(135, [5], [-4]),
  frame(150, [-4], [3]),
  frame(180, [0], [10]),
  frame(190, [10], [-6]),
  frame(205, [-6], [0]),
  frame(240, [-9], [9]),
  frame(246, [9], [-10]),
  frame(252, [-10], [8]),
  frame(258, [8], [-7]),
  frame(274, [-7], [0]),
  frame(300, [12], [15]),
  frame(330, [15], [12]),
  frame(360, [12], [12]),
]

const rootScale = [
  frame(0, [100, 100, 100], [103, 103, 100]),
  frame(30, [103, 103, 100], [100, 100, 100]),
  frame(60, [103, 103, 100], [109, 109, 100]),
  frame(76, [109, 109, 100], [103, 103, 100]),
  frame(120, [106, 106, 100], [111, 111, 100]),
  frame(150, [111, 111, 100], [106, 106, 100]),
  frame(180, [96, 96, 100], [118, 118, 100]),
  frame(191, [118, 118, 100], [102, 102, 100]),
  frame(215, [102, 102, 100], [108, 108, 100]),
  frame(240, [103, 103, 100], [103, 103, 100]),
  frame(300, [96, 96, 100], [94, 94, 100]),
  frame(330, [94, 94, 100], [96, 96, 100]),
  frame(360, [96, 96, 100], [96, 96, 100]),
]

const wingRotation = (side = 1) => {
  const flap = (start, end, low, high, step) => {
    const keys = []
    for (let t = start; t < end; t += step) {
      keys.push(frame(t, [side * low], [side * high]))
      keys.push(frame(Math.min(t + step / 2, end), [side * high], [side * low]))
    }
    return keys
  }

  return [
    ...flap(0, 60, -8, -30, 14),
    ...flap(60, 120, -18, -52, 10),
    ...flap(120, 180, -4, -72, 5),
    ...flap(180, 240, -28, -82, 8),
    ...flap(240, 300, -12, -60, 6),
    frame(300, [side * -4], [side * -18]),
    frame(330, [side * -18], [side * -4]),
    frame(360, [side * -4], [side * -4]),
  ]
}

const eyeScale = [
  frame(0, [100, 100, 100], [100, 100, 100]),
  frame(21, [100, 100, 100], [100, 8, 100]),
  frame(24, [100, 8, 100], [100, 100, 100]),
  frame(60, [100, 100, 100], [100, 100, 100]),
  frame(120, [100, 100, 100], [100, 120, 100]),
  frame(180, [100, 120, 100], [100, 100, 100]),
  frame(240, [115, 75, 100], [115, 75, 100]),
  frame(300, [100, 100, 100], [100, 0, 100]),
  hold(303, [100, 0, 100]),
  hold(360, [100, 0, 100]),
]

const bodyTeal = rgba('#35B9B3')
const bodyDark = rgba('#178D87')
const bodyLight = rgba('#73DED8')
const belly = rgba('#F9FEFD')
const lavender = rgba('#9B8AF8')
const magenta = rgba('#C2498C')
const amber = rgba('#F2B94B')
const red = rgba('#EF4444')
const ink = rgba('#122B2E')
const white = rgba('#FFFFFF')
const shadow = rgba('#0F172A', 0.2)

const layers = []
const mascotZoom = 1.18
const zoomScaleValue = (value) => [value[0] * mascotZoom, value[1] * mascotZoom, value[2]]
const zoomScaleFrames = (frames) => frames.map((item) => ({
  ...item,
  s: zoomScaleValue(item.s),
  ...(item.e ? { e: zoomScaleValue(item.e) } : {}),
}))

const rootIndex = ind
layers.push(nullLayer('state root hover keyframes', transform({
  anchor: [256, 256, 0],
  position: rootPosition,
  rotate: rootRotation,
  scale: zoomScaleFrames(rootScale),
})))

layers.push(baseLayer('soft oval shadow', rootIndex, [
  group('shadow', [ellipse('shadow ellipse', [178, 24]), fill(shadow, 28)]),
], transform({
  position: [250, 390, 0],
  scale: [
    frame(0, [100, 100, 100], [88, 88, 100]),
    frame(60, [90, 90, 100], [76, 76, 100]),
    frame(120, [82, 82, 100], [74, 74, 100]),
    frame(180, [110, 110, 100], [70, 70, 100]),
    frame(205, [70, 70, 100], [105, 105, 100]),
    frame(240, [92, 92, 100], [92, 92, 100]),
    frame(300, [112, 112, 100], [116, 116, 100]),
    frame(360, [112, 112, 100], [112, 112, 100]),
  ],
})))

layers.push(baseLayer('tail feathers', rootIndex, [
  group('tail left', [
    path('feather', [[-10, -8], [-74, -28], [-110, 20], [-32, 40], [8, 14]], [[0, 0], [0, 0], [-18, 18], [0, 0], [0, 0]], [[-18, -8], [-30, 10], [18, 12], [20, -4], [0, 0]]),
    fill(bodyDark, 100),
  ]),
  group('tail center', [
    path('feather', [[4, 0], [-66, 24], [-70, 72], [4, 40], [34, 14]], [[0, 0], [0, 0], [-4, 22], [0, 0], [0, 0]], [[-24, 14], [-10, 28], [20, 4], [12, -10], [0, 0]]),
    fill(bodyTeal, 95),
  ]),
], transform({
  position: [214, 302, 0],
  rotate: [
    frame(0, [-12], [-4]),
    frame(60, [-16], [-4]),
    frame(120, [-18], [8]),
    frame(180, [-4], [-20]),
    frame(240, [-22], [12]),
    frame(300, [18], [23]),
    frame(360, [18], [18]),
  ],
})))

layers.push(baseLayer('rear wing broad animated', rootIndex, [
  group('rear wing', [
    path(
      'wing',
      [[4, -12], [-76, -76], [-152, -42], [-112, 48], [-28, 56], [28, 18]],
      [[0, 0], [-22, -10], [-50, 20], [16, 46], [36, 18], [0, 0]],
      [[-30, -26], [-30, -30], [42, 34], [34, 28], [28, -8], [0, 0]],
    ),
    fill(rgba('#1FAAA3'), 96),
    stroke(rgba('#167F7A'), 3, 65),
  ]),
], transform({
  anchor: [202, 230, 0],
  position: [202, 230, 0],
  rotate: wingRotation(1),
})))

layers.push(baseLayer('body turquoise squash', rootIndex, [
  group('body fill', [
    ellipse('body oval', [144, 172]),
    fill(bodyTeal, 100),
    stroke(bodyDark, 4, 75),
  ]),
], transform({
  position: [258, 278, 0],
  rotate: [
    frame(0, [-5], [4]),
    frame(60, [-2], [5]),
    frame(120, [-5], [7]),
    frame(180, [0], [-9]),
    frame(240, [-10], [10]),
    frame(300, [8], [10]),
    frame(360, [8], [8]),
  ],
  scale: [
    frame(0, [100, 100, 100], [102, 98, 100]),
    frame(60, [102, 98, 100], [98, 104, 100]),
    frame(120, [100, 100, 100], [104, 96, 100]),
    frame(180, [96, 104, 100], [108, 92, 100]),
    frame(206, [108, 92, 100], [100, 100, 100]),
    frame(240, [102, 98, 100], [98, 102, 100]),
    frame(300, [96, 96, 100], [96, 96, 100]),
    frame(360, [96, 96, 100], [96, 96, 100]),
  ],
})))

layers.push(baseLayer('front wing bright animated', rootIndex, [
  group('front wing', [
    path(
      'wing',
      [[-6, -8], [74, -74], [146, -32], [106, 54], [24, 54], [-32, 16]],
      [[0, 0], [18, -18], [48, 18], [-12, 42], [-38, 18], [0, 0]],
      [[28, -28], [34, -28], [-40, 34], [-30, 26], [-30, -8], [0, 0]],
    ),
    fill(bodyLight, 95),
    stroke(bodyDark, 3, 45),
  ]),
], transform({
  anchor: [302, 232, 0],
  position: [302, 232, 0],
  rotate: wingRotation(-1),
})))

layers.push(baseLayer('white belly glow', rootIndex, [
  group('belly', [ellipse('belly oval', [76, 104]), fill(belly, 92)]),
], transform({
  position: [288, 298, 0],
  rotate: -8,
  scale: [
    frame(0, [100, 100, 100], [102, 96, 100]),
    frame(60, [102, 96, 100], [96, 104, 100]),
    frame(120, [100, 100, 100], [104, 94, 100]),
    frame(180, [98, 104, 100], [108, 92, 100]),
    frame(240, [100, 100, 100], [100, 100, 100]),
    frame(300, [92, 92, 100], [92, 92, 100]),
    frame(360, [92, 92, 100], [92, 92, 100]),
  ],
})))

layers.push(baseLayer('head expressive', rootIndex, [
  group('head', [
    ellipse('head oval', [118, 104]),
    fill(bodyLight, 100),
    stroke(bodyDark, 3.5, 72),
  ]),
], transform({
  position: [312, 206, 0],
  rotate: [
    frame(0, [-2], [3]),
    frame(60, [0], [-6]),
    frame(120, [8], [-10]),
    frame(150, [-10], [8]),
    frame(180, [0], [-8]),
    frame(240, [-12], [12]),
    frame(300, [12], [16]),
    frame(360, [12], [12]),
  ],
})))

layers.push(baseLayer('cheek magenta', rootIndex, [
  group('cheek', [ellipse('cheek', [28, 20]), fill(magenta, 72)]),
], transform({
  position: [331, 218, 0],
  rotate: -10,
  opacity: [
    frame(0, [76], [52]),
    frame(60, [70], [92]),
    frame(120, [82], [58]),
    frame(180, [100], [72]),
    frame(240, [100], [85]),
    frame(300, [40], [28]),
    frame(360, [40], [40]),
  ],
})))

layers.push(baseLayer('long beak lively', rootIndex, [
  group('beak lower', [
    path('beak', [[-8, 1], [92, 12], [8, 20]], [[0, 0], [0, 0], [0, 0]], [[28, 0], [-26, 8], [0, 0]], true),
    fill(rgba('#D8922B'), 100),
  ]),
  group('beak top', [
    path('beak', [[-10, -4], [110, -18], [6, 12]], [[0, 0], [0, 0], [0, 0]], [[34, -6], [-32, 10], [0, 0]], true),
    fill(amber, 100),
    stroke(rgba('#986317'), 2, 70),
  ]),
], transform({
  anchor: [350, 202, 0],
  position: [350, 202, 0],
  rotate: [
    frame(0, [0], [3]),
    frame(60, [1], [-7]),
    frame(120, [-8], [10]),
    frame(180, [-3], [-12]),
    frame(240, [-10], [12]),
    frame(300, [11], [13]),
    frame(360, [11], [11]),
  ],
})))

layers.push(baseLayer('open eye blink keyframes', rootIndex, [
  group('eye', [ellipse('eye black', [15, 18]), fill(ink, 100)]),
], transform({
  position: [324, 190, 0],
  scale: eyeScale,
})))

layers.push(baseLayer('eye highlight', rootIndex, [
  group('shine', [ellipse('shine', [5, 5]), fill(white, 95)]),
], transform({
  position: [327, 186, 0],
  scale: eyeScale,
})))

layers.push(baseLayer('closed sleepy eye', rootIndex, [
  group('closed eye', [
    path('closed eye curve', [[-12, 0], [0, 7], [14, 0]], [[0, 0], [-4, 3], [0, 0]], [[4, 4], [6, 2], [0, 0]], false),
    stroke(ink, 4, 100),
  ]),
], transform({
  position: [325, 193, 0],
  opacity: [
    hold(0, [0]),
    hold(21, [0]),
    hold(22, [100]),
    hold(27, [0]),
    hold(299, [0]),
    hold(300, [100]),
    hold(360, [100]),
  ],
})))

layers.push(baseLayer('tiny feet', rootIndex, [
  group('left foot', [
    path('foot', [[-16, 0], [-2, 10], [18, 2]], [[0, 0], [0, 0], [0, 0]], [[6, 7], [7, -6], [0, 0]], false),
    stroke(rgba('#8A5A17'), 4, 85),
  ]),
  group('right foot', [
    path('foot', [[12, 2], [24, 14], [42, 6]], [[0, 0], [0, 0], [0, 0]], [[4, 8], [7, -5], [0, 0]], false),
    stroke(rgba('#8A5A17'), 4, 85),
  ]),
], transform({
  position: [246, 370, 0],
  opacity: [
    frame(0, [72], [42]),
    frame(60, [45], [28]),
    frame(120, [35], [20]),
    frame(180, [55], [24]),
    frame(240, [70], [42]),
    frame(300, [78], [84]),
    frame(360, [78], [78]),
  ],
})))

for (const [idx, [x, y, color]] of [
  [0, [392, 132, lavender]],
  [1, [424, 98, bodyTeal]],
  [2, [370, 78, amber]],
]) {
  layers.push(baseLayer(`thinking bubble ${idx + 1}`, rootIndex, [
    group('bubble', [ellipse('dot', [14 + idx * 4, 14 + idx * 4]), fill(color, 88)]),
  ], transform({
    position: [x, y, 0],
    scale: [
      hold(0, [50, 50, 100]),
      frame(120 + idx * 5, [20, 20, 100], [120, 120, 100]),
      frame(140 + idx * 5, [120, 120, 100], [72, 72, 100]),
      frame(165 + idx * 5, [72, 72, 100], [118, 118, 100]),
      frame(180, [118, 118, 100], [50, 50, 100]),
      hold(181, [50, 50, 100]),
    ],
    opacity: opacityWindow(120 + idx * 4, 180, true),
  })))
}

for (const [idx, [x, y, r, color]] of [
  [0, [144, 122, 0, amber]],
  [1, [392, 116, 45, lavender]],
  [2, [170, 350, -25, magenta]],
  [3, [420, 330, 15, bodyTeal]],
]) {
  layers.push(baseLayer(`success sparkle ${idx + 1}`, rootIndex, [
    group('sparkle', [
      path('diamond', [[0, -18], [8, -4], [22, 0], [8, 5], [0, 20], [-8, 5], [-22, 0], [-8, -4]], [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]], [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]),
      fill(color, 92),
    ]),
  ], transform({
    position: [x, y, 0],
    rotate: [
      frame(180, [r], [r + 90]),
      frame(210, [r + 90], [r + 180]),
      frame(240, [r + 180], [r + 180]),
    ],
    scale: [
      frame(180, [10, 10, 100], [120, 120, 100]),
      frame(198, [120, 120, 100], [70, 70, 100]),
      frame(224, [70, 70, 100], [105, 105, 100]),
      frame(240, [105, 105, 100], [20, 20, 100]),
    ],
    opacity: opacityWindow(180, 239, true),
  })))
}

layers.push(baseLayer('alert exclamation badge', rootIndex, [
  group('badge', [ellipse('alert circle', [58, 58]), fill(red, 92), stroke(white, 4, 90)]),
  group('exclamation', [
    path('bar', [[-4, -18], [6, -18], [3, 8], [-1, 8]], [[0, 0], [0, 0], [0, 0], [0, 0]], [[0, 0], [0, 0], [0, 0], [0, 0]]),
    fill(white, 100),
    ellipse('dot', [9, 9], [1, 20]),
    fill(white, 100),
  ]),
], transform({
  position: [384, 128, 0],
  rotate: [
    frame(240, [-10], [10]),
    frame(250, [10], [-10]),
    frame(260, [-10], [8]),
    frame(280, [8], [0]),
    frame(300, [0], [0]),
  ],
  scale: [
    frame(240, [60, 60, 100], [120, 120, 100]),
    frame(252, [120, 120, 100], [92, 92, 100]),
    frame(300, [92, 92, 100], [92, 92, 100]),
  ],
  opacity: opacityWindow(240, 300, true),
})))

for (const [idx, [x, y, size]] of [
  [0, [382, 130, 18]],
  [1, [414, 96, 24]],
  [2, [446, 62, 31]],
]) {
  layers.push(baseLayer(`sleep z ${idx + 1}`, rootIndex, [
    group('z mark', [
      path('z', [[-16, -12], [14, -12], [-10, 12], [18, 12]], [[0, 0], [0, 0], [0, 0], [0, 0]], [[0, 0], [0, 0], [0, 0], [0, 0]], false),
      stroke(lavender, Math.max(4, size / 5), 92),
    ]),
  ], transform({
    position: [x, y, 0],
    scale: [
      hold(0, [45, 45, 100]),
      frame(300 + idx * 9, [40, 40, 100], [100, 100, 100]),
      frame(326 + idx * 9, [100, 100, 100], [70, 70, 100]),
      frame(356, [70, 70, 100], [110, 110, 100]),
      hold(360, [110, 110, 100]),
    ],
    opacity: opacityWindow(300 + idx * 8, 360, true),
  })))
}

const asset = {
  v: '5.12.2',
  fr: FR,
  ip: 0,
  op: TOTAL,
  w: 512,
  h: 512,
  nm: 'Kolibri cartoon living mascot',
  ddd: 0,
  assets: [],
  markers: [
    { tm: 0, cm: 'idle', dr: SEGMENT },
    { tm: 60, cm: 'ready', dr: SEGMENT },
    { tm: 120, cm: 'thinking', dr: SEGMENT },
    { tm: 180, cm: 'success', dr: SEGMENT },
    { tm: 240, cm: 'alert', dr: SEGMENT },
    { tm: 300, cm: 'sleeping', dr: SEGMENT },
  ],
  layers: layers.reverse(),
}

const manifest = {
  asset: '/mascot/kolibri-cartoon.json',
  type: 'lottie',
  renderer: 'canvas',
  fps: FR,
  size: { width: 512, height: 512 },
  states: {
    idle: { from: 0, to: 59 },
    ready: { from: 60, to: 119 },
    thinking: { from: 120, to: 179 },
    success: { from: 180, to: 239 },
    alert: { from: 240, to: 299 },
    error: { from: 240, to: 299 },
    sleeping: { from: 300, to: 359 },
  },
  generated_at: '2026-06-27T20:21:24Z',
}

await mkdir(outDir, { recursive: true })
await writeFile(outFile, `${JSON.stringify(asset)}\n`)
await writeFile(manifestFile, `${JSON.stringify(manifest, null, 2)}\n`)

console.log(`Generated ${outFile}`)
