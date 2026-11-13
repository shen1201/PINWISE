// 徽章外形：路徑都用絕對座標，等比縮放後可組成外框環。
export const SHAPE_PATHS = {
  circle: 'M120 1C185.7 1 239 54.3 239 120C239 185.7 185.7 239 120 239C54.3 239 1 185.7 1 120C1 54.3 54.3 1 120 1Z',
  hex: 'M108 8Q120 1 132 8L213 55Q224 62 224 75V165Q224 178 213 185L132 232Q120 239 108 232L27 185Q16 178 16 165V75Q16 62 27 55Z',
  shield: 'M120 3Q160 24 208 22Q220 22 220 34V112Q220 190 120 237Q20 190 20 112V34Q20 22 32 22Q80 24 120 3Z',
}
// V 指令只有 y，需要獨立處理；其他數字成對縮放。
export function scalePath(path, s) {
  const scale = (n) => (120 + (Number(n) - 120) * s).toFixed(2)
  return path.replace(/([MLQCVZ])([^MLQCVZ]*)/g, (_, cmd, args) => `${cmd}${args.trim().split(/[\s,]+/).filter(Boolean).map(scale).join(' ')}`)
}

// 金屬與琺瑯配色：徽章正面、背面、側邊共用。
export const METAL = {
  gold: { rim: ['#FFF9D9', '#EBC056', '#8A5608', '#FFEFA8', '#B57C1E', '#FFFBE0', '#E2AE3E', '#8F5E10'], wire: '#FBDD8A' },
  silver: { rim: ['#FFFFFF', '#CDD4DF', '#6C7586', '#F6F8FB', '#A2ABB9', '#FFFFFF', '#C5CCD8', '#7A8393'], wire: '#EDF1F6' },
  bronze: { rim: ['#FFE2CC', '#CF8354', '#6C381B', '#F6BE98', '#A5613A', '#FFE6D3', '#C77C4C', '#7B4423'], wire: '#EFB58E' },
}
export const ENAMEL = {
  verifier: ['#7BF0EA', '#1F86A8', '#0D4A70'], contrarian: ['#FFD08A', '#E8722F', '#8F2F18'], comparer: ['#CDB8FF', '#6E4FD0', '#2F1F7E'],
  etf: ['#9CF0BE', '#1E9E72', '#0B5A48'], detective: ['#9CC6FF', '#2A62D6', '#102A78'], guardian: ['#FFB0BE', '#D93A62', '#7A1238'],
  partner: ['#FFC4E0', '#E0559F', '#8A1F66'], streak: ['#E2F58A', '#62B032', '#1E6A2E'], split: ['#F2A6FF', '#A636C8', '#551070'],
  pause: ['#FFE28A', '#EFA21E', '#99500A'], honest: ['#A6EBFF', '#2AA6E0', '#0F5C96'], night: ['#6C7FD0', '#26347E', '#0C1238'],
  overlap: ['#A8F2E0', '#20A898', '#0C5A5C'], goal: ['#FFD6A0', '#F08A3E', '#B22E4E'],
}
export const LOWER = { silver: ['#D6D3FA', '#6461C9', '#37357F'], bronze: ['#F9D2AC', '#C96A45', '#7E3524'] }
