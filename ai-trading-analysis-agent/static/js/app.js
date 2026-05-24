// ========== MARKET DATA BY CATEGORY ==========
const MARKET_PAIRS = {
    crypto: {
        groups: [
            {
                label: 'Top 1-10 (Majors)',
                pairs: [
                    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT', 'SOL/USDT',
                    'ADA/USDT', 'DOGE/USDT', 'TRX/USDT', 'AVAX/USDT', 'LINK/USDT'
                ]
            },
            {
                label: 'Top 11-25 (Large Cap)',
                pairs: [
                    'DOT/USDT', 'TON/USDT', 'SHIB/USDT', 'XLM/USDT', 'SUI/USDT',
                    'HBAR/USDT', 'BCH/USDT', 'LTC/USDT', 'UNI/USDT', 'NEAR/USDT',
                    'APT/USDT', 'ICP/USDT', 'TAO/USDT', 'ETC/USDT', 'POL/USDT'
                ]
            },
            {
                label: 'Top 26-50 (Mid Cap)',
                pairs: [
                    'FIL/USDT', 'HYPE/USDT', 'STX/USDT', 'ATOM/USDT', 'IMX/USDT',
                    'AR/USDT', 'INJ/USDT', 'OP/USDT', 'PEPE/USDT', 'WIF/USDT',
                    'GRT/USDT', 'VET/USDT', 'RENDER/USDT', 'LDO/USDT',
                    'TIA/USDT', 'THETA/USDT', 'RUNE/USDT', 'SEI/USDT', 'AAVE/USDT',
                    'ALGO/USDT', 'MNT/USDT', 'QNT/USDT', 'ARB/USDT', 'BOME/USDT'
                ]
            },
            {
                label: 'Top 51-75 (Emerging/DeFi)',
                pairs: [
                    'FLOKI/USDT', 'FLOW/USDT', 'EGLD/USDT', 'GALA/USDT', 'SAND/USDT',
                    'NOT/USDT', 'AXS/USDT', 'XTZ/USDT', 'MINA/USDT', 'CHZ/USDT',
                    'NEO/USDT', 'ENJ/USDT', 'MANA/USDT', 'DOGS/USDT', 'SNX/USDT',
                    'XEC/USDT', 'IOTA/USDT', 'TURBO/USDT', 'MEW/USDT', 'ONDO/USDT',
                    'CRV/USDT', 'PEOPLE/USDT', 'FET/USDT', '1INCH/USDT', 'W/USDT'
                ]
            },
            {
                label: 'Top 76-100 (Small Cap)',
                pairs: [
                    'ROSE/USDT', 'CFX/USDT', 'JASMY/USDT', 'WLD/USDT', 'IOTX/USDT',
                    'ENA/USDT', 'JUP/USDT', 'LUNC/USDT', 'BONK/USDT', 'GMX/USDT',
                    'ZIL/USDT', 'BAT/USDT', 'PENDLE/USDT', 'COMP/USDT', 'ANKR/USDT',
                    'YFI/USDT', 'GLMR/USDT', 'ORDI/USDT', 'CELO/USDT', 'GNO/USDT',
                    'G/USDT', 'STRK/USDT', 'KNC/USDT', 'LRC/USDT', 'SUSHI/USDT'
                ]
            }
        ],
        defaultPair: 'BTC/USDT'
    },
    forex: {
        groups: [
            {
                label: 'Top 20 Forex',
                pairs: ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CHF', 'NZD/USD', 'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'NZD/JPY', 'CAD/JPY', 'CHF/JPY', 'EUR/AUD', 'EUR/CAD', 'EUR/CHF', 'GBP/AUD', 'GBP/CAD', 'GBP/CHF']
            }
        ],
        defaultPair: 'EUR/USD'
    },
    stocks: {
        groups: [
            {
                label: 'Top 20 Stocks',
                pairs: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'LLY', 'V', 'JPM', 'WMT', 'MA', 'UNH', 'JNJ', 'PG', 'HD', 'ORCL', 'COST', 'CRM']
            }
        ],
        defaultPair: 'AAPL'
    },
    index: {
        groups: [
            {
                label: 'Top 20 Index',
                pairs: ['SPX500', 'NAS100', 'DJI30', 'DAX40', 'FTSE100', 'JP225', 'EU50', 'FR40', 'AU200', 'US2000', 'HK33', 'IN50', 'SG30', 'TWIX', 'CN50', 'CH20', 'NL25', 'ES35', 'VIX', 'DXY']
            }
        ],
        defaultPair: 'SPX500'
    }
};

// ========== SMART PRICE FORMATTER ==========
const smartPrice = (val) => {
    const v = parseFloat(val);
    if (isNaN(v) || v === 0) return '$0.00';
    const abs = Math.abs(v);
    if (abs >= 1000)  return `$${v.toFixed(2)}`;
    if (abs >= 1)     return `$${v.toFixed(4)}`;
    if (abs >= 0.01)  return `$${v.toFixed(6)}`;
    // For micro-price coins (FLOKI, SHIB, PEPE, BONK, etc)
    // Show enough decimals to display significant digits
    const str = v.toFixed(20);
    const match = str.match(/^-?0\.0*/);
    const leadingZeros = match ? match[0].length - 2 : 0;
    const decimals = Math.max(leadingZeros + 4, 8);
    return `$${v.toFixed(decimals)}`;
};

// ========== CONTRACT SIZES (OKX SWAP) ==========
const CONTRACT_SIZES = {
    'BTC/USDT':  0.01,    // 1 kontrak = 0.01 BTC
    'ETH/USDT':  0.1,     // 1 kontrak = 0.1 ETH
    'XRP/USDT':  100,     // 1 kontrak = 100 XRP
    'BNB/USDT':  0.01,    // 1 kontrak = 0.01 BNB
    'SOL/USDT':  1,       // 1 kontrak = 1 SOL
    'ADA/USDT':  100,     // 1 kontrak = 100 ADA
    'DOGE/USDT': 1000,    // 1 kontrak = 1000 DOGE
    'TRX/USDT':  1000,    // 1 kontrak = 1000 TRX
    'AVAX/USDT': 1,       // 1 kontrak = 1 AVAX
    'LINK/USDT': 1,       // 1 kontrak = 1 LINK
    'DOT/USDT':  1,       // 1 kontrak = 1 DOT
    'TON/USDT':  1,       // 1 kontrak = 1 TON
    'SHIB/USDT': 1000000, // 1 kontrak = 1M SHIB
    'XLM/USDT':  100,     // 1 kontrak = 100 XLM
    'SUI/USDT':  1,       // 1 kontrak = 1 SUI
    'HBAR/USDT': 100,     // 1 kontrak = 100 HBAR
    'BCH/USDT':  0.1,     // 1 kontrak = 0.1 BCH
    'LTC/USDT':  1,       // 1 kontrak = 1 LTC
    'UNI/USDT':  1,       // 1 kontrak = 1 UNI
    'NEAR/USDT': 10,      // 1 kontrak = 10 NEAR
    'HYPE/USDT': 1,       // 1 kontrak = 1 HYPE
    'ARB/USDT':  10,      // 1 kontrak = 10 ARB
    'ONDO/USDT': 10,      // 1 kontrak = 10 ONDO
    'FET/USDT':  10,      // 1 kontrak = 10 FET
    'W/USDT':   10,      // 1 kontrak = 10 W
    'WLD/USDT':  1,       // 1 kontrak = 1 WLD
    'ENA/USDT':  10,      // 1 kontrak = 10 ENA
    'PENDLE/USDT': 1,     // 1 kontrak = 1 PENDLE
    'ORDI/USDT': 0.1,     // 1 kontrak = 0.1 ORDI
    'STRK/USDT': 10,      // 1 kontrak = 10 STRK
    'POL/USDT':  10,      // 1 kontrak = 10 POL
    'RENDER/USDT': 1,     // 1 kontrak = 1 RENDER
    'G/USDT':    100,     // 1 kontrak = 100 G
    'APT/USDT': 1, 'ICP/USDT': 1, 'TAO/USDT': 0.01, 'ETC/USDT': 10,
    'FIL/USDT': 10, 'STX/USDT': 10, 'ATOM/USDT': 10, 'IMX/USDT': 10, 
    'AR/USDT': 1, 'INJ/USDT': 1, 'OP/USDT': 10, 'PEPE/USDT': 1000000, 
    'WIF/USDT': 10, 'GRT/USDT': 100, 'VET/USDT': 1000, 'LDO/USDT': 10, 
    'TIA/USDT': 1, 'THETA/USDT': 10, 'RUNE/USDT': 1, 'SEI/USDT': 10, 
    'AAVE/USDT': 0.1, 'ALGO/USDT': 100, 'MNT/USDT': 10, 'QNT/USDT': 0.1, 'BOME/USDT': 1000,
    'FLOKI/USDT': 10000000, 'FLOW/USDT': 10, 'EGLD/USDT': 0.1, 'GALA/USDT': 100, 
    'SAND/USDT': 10, 'NOT/USDT': 1000, 'AXS/USDT': 0.1, 'XTZ/USDT': 10, 
    'MINA/USDT': 10, 'CHZ/USDT': 100, 'NEO/USDT': 1, 'ENJ/USDT': 10, 
    'MANA/USDT': 10, 'DOGS/USDT': 10000, 'SNX/USDT': 10, 'XEC/USDT': 10000, 
    'IOTA/USDT': 10, 'TURBO/USDT': 10000, 'MEW/USDT': 10000, 'CRV/USDT': 10, 
    'PEOPLE/USDT': 100, '1INCH/USDT': 10,
    'ROSE/USDT': 100, 'CFX/USDT': 10, 'JASMY/USDT': 100, 'IOTX/USDT': 100,
    'JUP/USDT': 100, 'LUNC/USDT': 1000000, 'BONK/USDT': 1000000, 'GMX/USDT': 0.1, 
    'ZIL/USDT': 1000, 'BAT/USDT': 100, 'COMP/USDT': 0.1, 'ANKR/USDT': 100, 
    'YFI/USDT': 0.001, 'GLMR/USDT': 10, 'CELO/USDT': 10, 'GNO/USDT': 0.1, 
    'KNC/USDT': 10, 'LRC/USDT': 10, 'SUSHI/USDT': 10,
    // Forex (standard lot sizes — 1 unit = 1 lot)
    'EUR/USD': 1, 'GBP/USD': 1, 'USD/JPY': 1, 'AUD/USD': 1, 'USD/CHF': 1,
    'NZD/USD': 1, 'USD/CAD': 1, 'EUR/GBP': 1, 'EUR/JPY': 1, 'GBP/JPY': 1,
    'AUD/JPY': 1, 'NZD/JPY': 1, 'CAD/JPY': 1, 'CHF/JPY': 1, 'EUR/AUD': 1,
    'EUR/CAD': 1, 'EUR/CHF': 1, 'GBP/AUD': 1, 'GBP/CAD': 1, 'GBP/CHF': 1,
    // Stocks (1 unit = 1 share)
    'AAPL': 1, 'MSFT': 1, 'GOOGL': 1, 'AMZN': 1, 'NVDA': 1,
    'META': 1, 'TSLA': 1, 'AVGO': 1, 'LLY': 1, 'V': 1, 
    'JPM': 1, 'WMT': 1, 'MA': 1, 'UNH': 1, 'JNJ': 1,
    'PG': 1, 'HD': 1, 'ORCL': 1, 'COST': 1, 'CRM': 1,
    // Index (1 unit = 1 contract)
    'SPX500': 1, 'NAS100': 1, 'DJI30': 1, 'DAX40': 1, 'FTSE100': 1,
    'JP225': 1, 'EU50': 1, 'FR40': 1, 'AU200': 1, 'US2000': 1, 
    'HK33': 1, 'IN50': 1, 'SG30': 1, 'TWIX': 1, 'CN50': 1,
    'CH20': 1, 'NL25': 1, 'ES35': 1, 'VIX': 1, 'DXY': 1
};

// ========== MAX LEVERAGES ==========
const MAX_LEVERAGES = {
    'BTC/USDT':  125,  'ETH/USDT':  100,
    'XRP/USDT':  75,   'BNB/USDT':  75,   'SOL/USDT':  75,
    'ADA/USDT':  75,   'DOGE/USDT': 75,   'TRX/USDT':  75,
    'AVAX/USDT': 50,   'LINK/USDT': 50,   'DOT/USDT':  50,
    'TON/USDT':  50,   'SHIB/USDT': 50,   'XLM/USDT':  50,
    'SUI/USDT':  50,   'HBAR/USDT': 50,   'BCH/USDT':  50,
    'LTC/USDT':  50,   'UNI/USDT':  50,   'NEAR/USDT': 50,
    'HYPE/USDT': 50,
    'ARB/USDT': 50, 'ONDO/USDT': 50, 'FET/USDT': 50, 'W/USDT': 50,
    'WLD/USDT': 50, 'ENA/USDT': 50, 'PENDLE/USDT': 50, 'ORDI/USDT': 50, 'STRK/USDT': 50,
    'POL/USDT': 50, 'RENDER/USDT': 50, 'G/USDT': 50,
    'APT/USDT': 50, 'ICP/USDT': 50, 'TAO/USDT': 50, 'ETC/USDT': 50,
    'FIL/USDT': 50, 'STX/USDT': 50, 'ATOM/USDT': 50, 'IMX/USDT': 50, 
    'AR/USDT': 20, 'INJ/USDT': 50, 'OP/USDT': 50, 'PEPE/USDT': 50, 
    'WIF/USDT': 50, 'GRT/USDT': 20, 'VET/USDT': 20, 'LDO/USDT': 50, 
    'TIA/USDT': 50, 'THETA/USDT': 20, 'RUNE/USDT': 20, 'SEI/USDT': 20, 
    'AAVE/USDT': 50, 'ALGO/USDT': 50, 'MNT/USDT': 20, 'QNT/USDT': 20, 'BOME/USDT': 50,
    'FLOKI/USDT': 20, 'FLOW/USDT': 20, 'EGLD/USDT': 20, 'GALA/USDT': 20, 
    'SAND/USDT': 20, 'NOT/USDT': 20, 'AXS/USDT': 20, 'XTZ/USDT': 20, 
    'MINA/USDT': 20, 'CHZ/USDT': 20, 'NEO/USDT': 20, 'ENJ/USDT': 20, 
    'MANA/USDT': 20, 'DOGS/USDT': 20, 'SNX/USDT': 20, 'XEC/USDT': 20, 
    'IOTA/USDT': 20, 'TURBO/USDT': 50, 'MEW/USDT': 50, 'CRV/USDT': 20, 
    'PEOPLE/USDT': 50, '1INCH/USDT': 20,
    'ROSE/USDT': 20, 'CFX/USDT': 20, 'JASMY/USDT': 20, 'IOTX/USDT': 20, 
    'JUP/USDT': 20, 'LUNC/USDT': 20, 'BONK/USDT': 20, 'GMX/USDT': 20, 
    'ZIL/USDT': 20, 'BAT/USDT': 20, 'COMP/USDT': 20, 'ANKR/USDT': 20, 
    'YFI/USDT': 20, 'GLMR/USDT': 20, 'CELO/USDT': 20, 'GNO/USDT': 20, 
    'KNC/USDT': 20, 'LRC/USDT': 20, 'SUSHI/USDT': 20,
    'EUR/USD': 500, 'GBP/USD': 500, 'USD/JPY': 500, 'AUD/USD': 500, 'USD/CHF': 500,
    'AAPL': 20, 'MSFT': 20, 'GOOGL': 20, 'AMZN': 20, 'NVDA': 20,
    'SPX500': 100, 'NAS100': 100, 'DJI30': 100, 'DAX40': 100, 'FTSE100': 100
};

// ========== STATE ==========
let currentPrice = 0.0;
let currentMarket = 'crypto';
let currentCacheId = null;

// ========== APP ==========
document.addEventListener('DOMContentLoaded', () => {
    const pairSelect = document.getElementById('pair');
    const limitSelect = document.getElementById('limit');
    const timeframeSelect = document.getElementById('timeframe');
    const styleSelect = document.getElementById('style');
    const btnAnalyze = document.getElementById('btn-analyze');
    
    const execSize = document.getElementById('exec-size');
    const execLev = document.getElementById('exec-leverage');
    const marginEst = document.getElementById('margin-est');
    const sizeHint = document.getElementById('size-hint');
    
    const btnLong = document.getElementById('btn-long');
    const btnShort = document.getElementById('btn-short');
    
    const terminalOutput = document.getElementById('terminal-output');

    // ========== MARKET TAB SWITCHING ==========
    function populatePairDropdown(market) {
        const data = MARKET_PAIRS[market];
        pairSelect.innerHTML = '';

        data.groups.forEach(group => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = group.label;
            group.pairs.forEach(pair => {
                const option = document.createElement('option');
                option.value = pair;
                option.textContent = pair;
                if (pair === data.defaultPair) option.selected = true;
                optgroup.appendChild(option);
            });
            pairSelect.appendChild(optgroup);
        });

        updateMarginPreview();
    }

    document.querySelectorAll('.market-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.market-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            currentMarket = tab.dataset.market;
            populatePairDropdown(currentMarket);
        });
    });

    // ========== MARGIN / PREVIEW ==========
    const updateMarginPreview = () => {
        const pair = pairSelect.value;
        const maxLevAllowed = MAX_LEVERAGES[pair] || 50;
        
        // Filter leverage dropdown options
        Array.from(execLev.options).forEach(opt => {
            if (parseInt(opt.value) > maxLevAllowed) {
                opt.disabled = true;
                opt.style.display = 'none';
            } else {
                opt.disabled = false;
                opt.style.display = 'block';
            }
        });
        
        let lev = parseFloat(execLev.value) || 1;
        if (lev > maxLevAllowed) {
            execLev.value = maxLevAllowed.toString();
            lev = maxLevAllowed;
        }

        const size = parseFloat(execSize.value) || 0;
        
        let multiplier = 1;
        let hintText = '1 Unit = 1 Kontrak';
        
        // Find contract size (exact match only to prevent false positives like G matching EGLD)
        if (CONTRACT_SIZES[pair] !== undefined) {
            multiplier = CONTRACT_SIZES[pair];
            const coinName = pair.includes('/') ? pair.split('/')[0] : pair;
            if (multiplier >= 1000) {
                hintText = `1 Kontrak = ${multiplier.toLocaleString()} ${coinName}`;
            } else {
                hintText = `1 Kontrak = ${multiplier} ${coinName}`;
            }
        }
        
        sizeHint.textContent = hintText;
        
        if (currentPrice > 0) {
            const notional = currentPrice * multiplier * size;
            const margin = notional / lev;
            marginEst.textContent = `$${margin.toFixed(3)}`;
        } else {
            marginEst.textContent = '$0.00';
        }
    };

    pairSelect.addEventListener('change', updateMarginPreview);
    execSize.addEventListener('input', updateMarginPreview);
    execLev.addEventListener('input', updateMarginPreview);

    // ========== TOAST ==========
    const showToast = (msg, type='success') => {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.className = `toast show ${type}`;
        setTimeout(() => toast.className = 'toast', 4000);
    };

    // ========== ANALYZE ==========
    btnAnalyze.addEventListener('click', async () => {
        btnAnalyze.disabled = true;
        btnAnalyze.textContent = 'Analyzing...';
        terminalOutput.textContent = '[*] Mengambil data market dari server TradingView...\n[*] AI Engine sedang mengekstraksi struktur pasar dan likuiditas!\n[*] Harap tunggu beberapa detik...';
        
        try {
            const res = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pair: pairSelect.value.toUpperCase(),
                    timeframe: timeframeSelect.value,
                    limit: parseInt(limitSelect.value),
                    style: styleSelect.value
                })
            });
            
            const data = await res.json();
            
            if (data.success) {
                currentCacheId = data.cache_id || null;
                terminalOutput.textContent = data.formatted_report;
                
                // Update Setup Detail Cards
                const summary = data.summary;
                currentPrice = summary.price;
                
                document.getElementById('summary-price').textContent = smartPrice(currentPrice);
                document.getElementById('summary-trend').textContent = summary.trend;
                
                let biasStr = summary.preferred.toUpperCase();
                if (biasStr === 'LONG') biasStr += ` (${(summary.probability_bull).toFixed(0)}%)`;
                if (biasStr === 'SHORT') biasStr += ` (${(summary.probability_bear).toFixed(0)}%)`;
                
                const es = data.executive_summary || {};
                const conf = data.confidence_metrics || {};
                let score = parseFloat(conf.final_conviction) || 0;
                
                // Force score 0 if expired/halted
                if (es.action && (es.action.includes("HALTED") || es.action.includes("RECALIBRATING") || es.action.includes("RISK OFF"))) {
                    score = 0;
                }

                const biasEl = document.getElementById('summary-bias');
                biasEl.textContent = es.bias || biasStr;
                biasEl.style.color = summary.preferred === 'long' ? 'var(--success)' : summary.preferred === 'short' ? 'var(--danger)' : 'var(--text-main)';

                // Update ECharts Gauge
                if (typeof echarts !== 'undefined') {
                    let myChart = echarts.getInstanceByDom(document.getElementById('conviction-gauge'));
                    if (!myChart) myChart = echarts.init(document.getElementById('conviction-gauge'));

                    myChart.setOption({
                        series: [{
                            type: 'gauge',
                            startAngle: 180, endAngle: 0,
                            min: 0, max: 100,
                            axisLine: {
                                lineStyle: {
                                    width: 15,
                                    color: [[0.3, '#ff1744'], [0.7, '#ffea00'], [1, '#00e676']]
                                }
                            },
                            pointer: { itemStyle: { color: '#00f3ff' } },
                            axisTick: { distance: -20, length: 8, lineStyle: { color: '#fff', width: 1 } },
                            splitLine: { distance: -25, length: 15, lineStyle: { color: '#fff', width: 2 } },
                            axisLabel: { color: '#8b949e', distance: 15, fontSize: 10 },
                            detail: { valueAnimation: true, formatter: '{value}%', color: '#fff', fontSize: 28, offsetCenter: [0, '40%'] },
                            data: [{ value: score }]
                        }]
                    });

                    // Action text under gauge
                    const al = document.getElementById('action-label');
                    al.textContent = es.action || "STANDBY";
                    al.style.color = (es.action && es.action.includes("ENTER")) ? "var(--success)" : 
                                     (es.action && (es.action.includes("RISK") || es.action.includes("HALT"))) ? "var(--danger)" : "var(--text-main)";
                }

                // Update Glow Badges
                const setBadge = (id, htmlStr) => {
                    const el = document.getElementById(id);
                    if (!el) return;
                    htmlStr = htmlStr || "N/A";
                    el.querySelector('.badge-value').innerHTML = htmlStr;
                    
                    el.className = 'macro-badge';
                    if (htmlStr.includes('🔴')) el.classList.add('glow-red');
                    else if (htmlStr.includes('🟡')) el.classList.add('glow-yellow');
                    else if (htmlStr.includes('🟢')) el.classList.add('glow-green');
                };
                
                if (es) {
                    setBadge('vix-badge', es.vix_str);
                    setBadge('dxy-badge', es.dxy_str);
                    setBadge('spx-badge', es.spx_str);
                    setBadge('conflict-badge', es.conflict);
                }


                // Fetch Long/Short Setups
                const lSetup = summary.long_setup || {};
                const sSetup = summary.short_setup || {};

                // Map Long Limits
                if (lSetup.entry) {
                    document.getElementById('long-entry').textContent = smartPrice(lSetup.entry);
                    document.getElementById('long-sl').textContent = smartPrice(lSetup.stop_loss);
                    document.getElementById('long-tp1').textContent = smartPrice(lSetup.take_profit);
                    
                    const tpDist = (Math.abs(lSetup.take_profit - lSetup.entry) / lSetup.entry) * 100;
                    const slDist = (Math.abs(lSetup.entry - lSetup.stop_loss) / lSetup.entry) * 100;
                    document.getElementById('long-est').textContent = `+${tpDist.toFixed(2)}% / -${slDist.toFixed(2)}%`;
                } else {
                    document.getElementById('long-est').textContent = '+0.0% / -0.0%';
                }

                // Map Short Limits
                if (sSetup.entry) {
                    document.getElementById('short-entry').textContent = smartPrice(sSetup.entry);
                    document.getElementById('short-sl').textContent = smartPrice(sSetup.stop_loss);
                    document.getElementById('short-tp1').textContent = smartPrice(sSetup.take_profit);
                    
                    const tpDist = (Math.abs(sSetup.take_profit - sSetup.entry) / sSetup.entry) * 100;
                    const slDist = (Math.abs(sSetup.entry - sSetup.stop_loss) / sSetup.entry) * 100;
                    document.getElementById('short-est').textContent = `+${tpDist.toFixed(2)}% / -${slDist.toFixed(2)}%`;
                } else {
                    document.getElementById('short-est').textContent = '+0.0% / -0.0%';
                }

                // Handle Display Logic (If Recalibrating, dim limits but keep numbers visible)
                if (score === 0) {
                    document.getElementById('long-setup-card').style.opacity = '0.35';
                    document.getElementById('short-setup-card').style.opacity = '0.35';
                    document.getElementById('long-setup-card').style.border = '1px solid var(--danger)';
                    document.getElementById('short-setup-card').style.border = '1px solid var(--danger)';
                } else {
                    document.getElementById('long-setup-card').style.opacity = '1';
                    document.getElementById('short-setup-card').style.opacity = '1';
                    document.getElementById('long-setup-card').style.border = 'none';
                    document.getElementById('short-setup-card').style.border = 'none';
                }


                // Enable execution buttons
                btnLong.disabled = false;
                btnShort.disabled = false;
                
                updateMarginPreview();
                showToast('Analisa AI Selesai!');
            } else {
                throw new Error(data.error);
            }
        } catch (e) {
            terminalOutput.textContent = `[!] Error terjadi pada sistem AI:\n${e.message}`;
            showToast('Gagal melakukan kalkulasi AI', 'error');
        } finally {
            btnAnalyze.disabled = false;
            btnAnalyze.textContent = 'Generate Analysis';
        }
    });

    // ========== EXECUTE ==========
    const executeTrade = async (side) => {
        if (!confirm(`Tembak pesanan eksekusi ${side.toUpperCase()} ke OKX sekarang?`)) return;
        
        const btn = side === 'long' ? btnLong : btnShort;
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '...';
        
        try {
            const res = await fetch('/api/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    side: side,
                    leverage: parseFloat(execLev.value),
                    order_size: parseInt(execSize.value),
                    cache_id: currentCacheId
                })
            });
            
            const data = await res.json();
            if (data.success) {
                showToast(data.message, 'success');
                terminalOutput.textContent += `\n\n[API OKX] SUCCESS: ${data.message}`;
            } else {
                throw new Error(data.error);
            }
        } catch (e) {
            showToast(e.message, 'error');
            terminalOutput.textContent += `\n\n[API OKX] ERROR: ${e.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    };

    btnLong.addEventListener('click', () => executeTrade('long'));
    btnShort.addEventListener('click', () => executeTrade('short'));
    
    // ========== INIT ==========
    populatePairDropdown('crypto');
    updateMarginPreview();
});
