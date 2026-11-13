// 預估投入金額：[選項, 上限（元，null 代表沒有上限或不想填）]
export const BUDGET_OPTIONS = [['1 萬以下', 10_000], ['1～10 萬', 100_000], ['10～50 萬', 500_000], ['50 萬以上', null], ['不想填', null]]

// 個人化偏好問卷題目（搬自 js/settings.js 的 preferenceQuestions）：[欄位, 題目, 選項]
export const PREFERENCE_QUESTIONS = [
  ['explanationStyle', '希望內容怎麼說明？', ['清楚易懂', '重點分析', '專業深入']],
  ['horizon', '通常會觀察多久？', ['短期', '中期', '長期', '沒有固定期間']],
  ['riskTolerance', '持有標的下跌時，你較接近哪種感受？', ['較難接受', '可接受小幅波動', '可接受明顯波動', '能承受較大波動']],
  ['objective', '目前最重視什麼？', ['穩定成長', '資產增值', '股息收入', '掌握產業機會']],
  ['liquidity', '這筆資金近期可能使用嗎？', ['可能短期使用', '暫時不會使用', '可長期投入']],
  // 只用來在選股卡片換算「一張大約多少錢、占預估金額多少」，不會用來建議買幾張。
  ['budget', '這次大約打算投入多少？', BUDGET_OPTIONS.map(([label]) => label)],
]

// 偏好摘要的顯示名稱
export const PREFERENCE_LABELS = { explanationStyle: '說明方式', horizon: '觀察期間', riskTolerance: '波動感受', objective: '主要目標', liquidity: '資金需求', budget: '預估投入' }
