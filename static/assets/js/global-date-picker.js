/*
 * Mero Attendance global calendar system.
 * The organization setting controls every date input:
 *   window.ORG_DATE_TYPE = "nepali" -> BS picker with AD hidden value when needed
 *   anything else / missing        -> English YYYY-MM-DD picker
 *
 * The BS picker is a small self-contained popup (see openBsPopup below) rather
 * than the third-party jquery.nepaliDatePicker plugin. That plugin formats/parses
 * dates using Devanagari numerals only (getNepaliNumber/getNumberByNepaliNumber)
 * and a "%y-%m-%d" style token format - fundamentally incompatible with the plain
 * Arabic-numeral "YYYY-MM-DD" strings used everywhere else in this app (Python's
 * nepali_datetime, form submission, hidden AD fields). Feeding it our values threw
 * "Missing required parameters" and froze the page on every date selection.
 */
(function (global, document) {
    'use strict';

    var INIT_ATTR = 'data-global-date-picker-init';
    var MODE_ATTR = 'data-global-date-picker-mode';
    var WARNING_KEY = '__meroDatePickerWarned';
    var mutationTimer = null;
    var isInitializing = false;

    function normalizedMode() {
        var raw = String(global.ORG_DATE_TYPE || '').trim().toLowerCase();
        return raw === 'nepali' || raw === 'bs' ? 'nepali' : 'english';
    }

    function pad2(value) {
        return String(value).padStart(2, '0');
    }

    function asYmd(obj) {
        if (!obj) return '';
        return obj.year + '-' + pad2(obj.month) + '-' + pad2(obj.day);
    }

    function parseYmd(value) {
        var parts = String(value || '').trim().split('-');
        if (parts.length !== 3) return null;
        var year = parseInt(parts[0], 10);
        var month = parseInt(parts[1], 10);
        var day = parseInt(parts[2], 10);
        if (!year || !month || !day) return null;
        return { year: year, month: month, day: day };
    }

    // Self-contained BS<->AD conversion. This table is machine-generated
    // directly from the authoritative `nepali_datetime` Python library's own
    // calendar data (nepali_datetime/data/calendar_bs.csv) - do not hand-edit,
    // regenerate from that CSV instead. Covers every BS year the library
    // supports (1975-2100, i.e. every AD date from 1918-04-13 to 2044-04-12),
    // so real month lengths are used for any realistic date of birth,
    // admission date, or calendar entry - not just a narrow recent window.
    // Mirrors nothing else now: templates/admin/calendar.html used to keep
    // its own separate (smaller, drifted) copy of this table, which is why
    // dates outside ~2075-2092 could land on the wrong weekday there; it now
    // delegates to window.NepaliDate (exported below) instead of duplicating
    // this data, so there is exactly one source of truth for the whole app.
    var BS_MONTH_DATA = {
        1975: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        1976: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        1977: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        1978: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1979: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        1980: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        1981: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        1982: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1983: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        1984: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        1985: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        1986: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1987: [31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        1988: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        1989: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        1990: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1991: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        1992: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        1993: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1994: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1995: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        1996: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        1997: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1998: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        1999: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2000: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2001: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2002: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2003: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2004: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2005: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2006: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2007: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2008: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31],
        2009: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2010: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2011: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2012: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        2013: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2014: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2015: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2016: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        2017: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2018: [31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2019: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2020: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2021: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2022: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2023: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2024: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2025: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2026: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2027: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2028: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2029: [31, 31, 32, 31, 32, 30, 30, 29, 30, 29, 30, 30],
        2030: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2031: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2032: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2033: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2034: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2035: [30, 32, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31],
        2036: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2037: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2038: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2039: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        2040: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2041: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2042: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2043: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        2044: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2045: [31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2046: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2047: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2048: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2049: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2050: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2051: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2052: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2053: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2054: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2055: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2056: [31, 31, 32, 31, 32, 30, 30, 29, 30, 29, 30, 30],
        2057: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2058: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2059: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2060: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2061: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2062: [31, 31, 31, 32, 31, 31, 29, 30, 29, 30, 29, 31],
        2063: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2064: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2065: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2066: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31],
        2067: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2068: [31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2069: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2070: [31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30],
        2071: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2072: [31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2073: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31],
        2074: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2075: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2076: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2077: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2078: [31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30],
        2079: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2080: [31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30],
        2081: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31],
        2082: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2083: [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30],
        2084: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30],
        2085: [31, 32, 31, 32, 30, 31, 30, 30, 29, 30, 30, 30],
        2086: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2087: [31, 31, 32, 31, 31, 31, 30, 29, 30, 30, 30, 30],
        2088: [30, 31, 32, 32, 30, 31, 30, 30, 29, 30, 30, 30],
        2089: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2090: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2091: [31, 31, 32, 31, 31, 31, 30, 30, 29, 30, 30, 30],
        2092: [30, 31, 32, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2093: [30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2094: [31, 31, 32, 31, 31, 30, 30, 30, 29, 30, 30, 30],
        2095: [31, 31, 32, 31, 31, 31, 30, 29, 30, 30, 30, 30],
        2096: [30, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30],
        2097: [31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 30, 30],
        2098: [31, 31, 32, 31, 31, 31, 29, 30, 29, 30, 29, 31],
        2099: [31, 31, 32, 31, 31, 31, 30, 29, 29, 30, 30, 30],
        2100: [31, 32, 31, 32, 30, 31, 30, 29, 30, 29, 30, 30]
    };
    // Last-resort fallback for any BS year outside 1975-2100 (i.e. an AD date
    // before 1918-04-13 or after 2044-04-12) - not a realistic date of birth,
    // admission date, or calendar entry, but kept so the picker degrades
    // gracefully instead of throwing. Reuses 2075's real pattern (sums to
    // 365, unlike the very first version of this fallback which summed to
    // 367 and silently drifted computed AD dates by ~2 days/year).
    var BS_MONTH_FALLBACK = [31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30];
    var BS_EPOCH_YEAR = 2079;
    var BS_EPOCH_AD = new Date(2022, 3, 14); // 2079 Baisakh 1 = 2022-04-14
    var NP_MONTHS = ['Baisakh', 'Jestha', 'Ashadh', 'Shrawan', 'Bhadra', 'Ashwin',
        'Kartik', 'Mangsir', 'Poush', 'Magh', 'Falgun', 'Chaitra'];

    function bsMonthLengths(year) {
        return BS_MONTH_DATA[year] || BS_MONTH_FALLBACK;
    }

    function bsToAdDate(bsY, bsM, bsD) {
        var days = 0;
        var y;
        if (bsY >= BS_EPOCH_YEAR) {
            for (y = BS_EPOCH_YEAR; y < bsY; y += 1) {
                days += bsMonthLengths(y).reduce(function (a, b) { return a + b; }, 0);
            }
        } else {
            for (y = bsY; y < BS_EPOCH_YEAR; y += 1) {
                days -= bsMonthLengths(y).reduce(function (a, b) { return a + b; }, 0);
            }
        }
        var months = bsMonthLengths(bsY);
        for (var m = 1; m < bsM; m += 1) days += months[m - 1];
        days += bsD - 1;
        var ad = new Date(BS_EPOCH_AD);
        ad.setDate(ad.getDate() + days);
        return ad;
    }

    function adDateToBs(adDate) {
        var diff = Math.round((adDate - BS_EPOCH_AD) / 86400000);
        var bsY = BS_EPOCH_YEAR;
        if (diff >= 0) {
            while (true) {
                var total = bsMonthLengths(bsY).reduce(function (a, b) { return a + b; }, 0);
                if (diff < total) break;
                diff -= total;
                bsY += 1;
            }
        } else {
            while (diff < 0) {
                bsY -= 1;
                diff += bsMonthLengths(bsY).reduce(function (a, b) { return a + b; }, 0);
            }
        }
        var months = bsMonthLengths(bsY);
        var bsM = 1;
        while (bsM <= 12 && diff >= months[bsM - 1]) { diff -= months[bsM - 1]; bsM += 1; }
        return { year: bsY, month: bsM, day: diff + 1 };
    }

    function bs2ad(bsValue) {
        var parsed = parseYmd(bsValue);
        if (!parsed) return '';
        try {
            var ad = bsToAdDate(parsed.year, parsed.month, parsed.day);
            return asYmd({ year: ad.getFullYear(), month: ad.getMonth() + 1, day: ad.getDate() });
        } catch (err) {
            return '';
        }
    }

    function ad2bs(adValue) {
        var parsed = parseYmd(adValue);
        if (!parsed) return '';
        try {
            var adDate = new Date(parsed.year, parsed.month - 1, parsed.day);
            return asYmd(adDateToBs(adDate));
        } catch (err) {
            return '';
        }
    }

    function currentBsDate() {
        try {
            return asYmd(adDateToBs(new Date()));
        } catch (err) {
            return '';
        }
    }

    function dispatchNative(input) {
        ['input', 'change'].forEach(function (eventName) {
            input.dispatchEvent(new Event(eventName, { bubbles: true }));
        });
    }

    function warnOnce(message) {
        if (global[WARNING_KEY]) return;
        global[WARNING_KEY] = true;
        if (global.console && console.warn) console.warn(message);
    }

    function isHidden(input) {
        return input.type === 'hidden' || input.classList.contains('hidden-date-input');
    }

    function candidateSelector() {
        return [
            'input[type="date"]',
            'input.global-date-picker',
            'input.date-input',
            'input.date-picker',
            'input.datepicker',
            'input.eng-cal',
            'input.nepali-cal',
            'input.nepali-trigger',
            'input[name$="_np"]',
            'input[id="force-nepali-cal"]',
            'input[id="english-datepicker"]',
            'input[data-global-date-picker]'
        ].join(',');
    }

    function ensureClass(input) {
        input.classList.add('global-date-picker');
    }

    function ensureWrapper(input) {
        if (!input.parentNode || input.parentNode.classList.contains('global-date-wrap')) return;
        if (input.closest('.flatpickr-wrapper')) return;

        var wrapper = document.createElement('span');
        wrapper.className = 'global-date-wrap';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        var icon = document.createElement('span');
        icon.className = 'global-date-icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.innerHTML = '<i class="fas fa-calendar-alt"></i>';
        wrapper.appendChild(icon);
    }

    function pairedHiddenInput(input) {
        var form = input.form || input.closest('form');
        if (!form || !input.name) return null;

        var names = [];
        if (input.name.slice(-3) === '_np') names.push(input.name.slice(0, -3));
        if (input.name.slice(-11) === '_np_display') names.push(input.name.slice(0, -11));

        for (var i = 0; i < names.length; i += 1) {
            var escaped = names[i].replace(/"/g, '\\"');
            var match = form.querySelector('input[type="hidden"][name="' + escaped + '"], input.hidden-date-input[name="' + escaped + '"]');
            if (match) return match;
        }
        return null;
    }

    function syncNepaliValue(input) {
        if (input.__syncInProgress) return;
        input.__syncInProgress = true;

        try {
            var bsValue = String(input.value || '').trim();
            input.value = bsValue;
            var hidden = input.__globalDateHidden || pairedHiddenInput(input);
            if (hidden) {
                var adValue = bsValue ? (bs2ad(bsValue) || hidden.value || bsValue) : '';
                if (hidden.value !== adValue) {
                    hidden.value = adValue;
                    dispatchNative(hidden);
                }
            }
            dispatchNative(input);
        } finally {
            input.__syncInProgress = false;
        }
    }

    function destroyFlatpickr(input) {
        if (input && input._flatpickr && typeof input._flatpickr.destroy === 'function') {
            try { input._flatpickr.destroy(); } catch (err) {}
        }
    }

    // ── Custom BS calendar popup (no third-party plugin) ──────────────────
    var bsPopup = null;
    var bsPopupTarget = null;
    var bsPopupView = null; // { year, month }

    function seedBsValue(input) {
        var bsValue = String(input.value || '').trim();
        if (bsValue) return bsValue;

        var hidden = input.__globalDateHidden || pairedHiddenInput(input);
        if (hidden && hidden.value) {
            var converted = ad2bs(hidden.value);
            if (converted) return converted;
        }

        return currentBsDate();
    }

    function ensureBsPopup() {
        if (bsPopup) return bsPopup;
        var el = document.createElement('div');
        el.className = 'global-bs-popup';
        el.setAttribute('role', 'dialog');
        el.style.display = 'none';
        document.body.appendChild(el);
        el.addEventListener('mousedown', function (e) { e.stopPropagation(); });
        bsPopup = el;
        return el;
    }

    function closeBsPopup() {
        if (bsPopup) bsPopup.style.display = 'none';
        bsPopupTarget = null;
        bsPopupView = null;
    }

    function renderBsPopup() {
        if (!bsPopup || !bsPopupView) return;
        var year = bsPopupView.year;
        var month = bsPopupView.month;
        var monthLen = bsMonthLengths(year)[month - 1];
        var firstOfMonthAd = bsToAdDate(year, month, 1);
        var startDow = firstOfMonthAd.getDay(); // 0=Sun

        var selected = parseYmd(bsPopupTarget ? bsPopupTarget.value : '');
        // Most date fields (report filters, leave dates, etc.) only ever need
        // to move a few years from today, so the default stays a tight ±10
        // window. Fields that legitimately span decades (date of birth, an
        // old/planned admission date) can opt into a wider one-click range
        // via data-year-span-back / data-year-span-forward on the input.
        var spanBack = 10;
        var spanForward = 10;
        if (bsPopupTarget) {
            var attrBack = parseInt(bsPopupTarget.getAttribute('data-year-span-back'), 10);
            var attrForward = parseInt(bsPopupTarget.getAttribute('data-year-span-forward'), 10);
            if (!isNaN(attrBack)) spanBack = attrBack;
            if (!isNaN(attrForward)) spanForward = attrForward;
        }
        var yearOptions = '';
        for (var y = year - spanBack; y <= year + spanForward; y += 1) {
            yearOptions += '<option value="' + y + '"' + (y === year ? ' selected' : '') + '>' + y + '</option>';
        }
        var monthOptions = '';
        for (var m = 0; m < 12; m += 1) {
            monthOptions += '<option value="' + (m + 1) + '"' + (m + 1 === month ? ' selected' : '') + '>' + NP_MONTHS[m] + '</option>';
        }

        var html = '<div class="global-bs-popup-header">'
            + '<button type="button" class="global-bs-nav" data-nav="-1" aria-label="Previous month">&lsaquo;</button>'
            + '<select class="global-bs-month-select">' + monthOptions + '</select>'
            + '<select class="global-bs-year-select">' + yearOptions + '</select>'
            + '<button type="button" class="global-bs-nav" data-nav="1" aria-label="Next month">&rsaquo;</button>'
            + '</div>'
            + '<div class="global-bs-popup-grid">';

        ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].forEach(function (d) {
            html += '<div class="global-bs-dow">' + d + '</div>';
        });

        for (var i = 0; i < startDow; i += 1) html += '<div class="global-bs-day is-empty"></div>';
        for (var d = 1; d <= monthLen; d += 1) {
            var isSelected = selected && selected.year === year && selected.month === month && selected.day === d;
            html += '<div class="global-bs-day' + (isSelected ? ' is-selected' : '') + '" data-day="' + d + '">' + d + '</div>';
        }

        html += '</div><div class="global-bs-popup-footer">'
            + '<button type="button" class="global-bs-today">Today</button>'
            + '</div>';

        bsPopup.innerHTML = html;
    }

    function positionBsPopup(input) {
        var rect = input.getBoundingClientRect();
        var scrollX = global.scrollX || document.documentElement.scrollLeft;
        var scrollY = global.scrollY || document.documentElement.scrollTop;
        bsPopup.style.position = 'absolute';
        bsPopup.style.top = (rect.bottom + scrollY + 4) + 'px';
        bsPopup.style.left = (rect.left + scrollX) + 'px';
        bsPopup.style.zIndex = 3000;

        // Keep on-screen horizontally
        var popupWidth = bsPopup.offsetWidth || 260;
        var viewportWidth = document.documentElement.clientWidth;
        var left = rect.left + scrollX;
        if (left + popupWidth > scrollX + viewportWidth - 8) {
            left = scrollX + viewportWidth - popupWidth - 8;
        }
        bsPopup.style.left = Math.max(scrollX + 8, left) + 'px';
    }

    function openBsPopup(input) {
        ensureBsPopup();
        bsPopupTarget = input;

        var seeded = seedBsValue(input);
        var parsed = parseYmd(seeded) || (function () { var t = parseYmd(currentBsDate()); return t; })();
        bsPopupView = { year: parsed.year, month: parsed.month };

        renderBsPopup();
        bsPopup.style.display = 'block';
        positionBsPopup(input);
    }

    function selectBsDay(day) {
        if (!bsPopupTarget || !bsPopupView) return;
        var value = asYmd({ year: bsPopupView.year, month: bsPopupView.month, day: day });
        bsPopupTarget.value = value;
        syncNepaliValue(bsPopupTarget);
        closeBsPopup();
    }

    function shiftBsMonth(delta) {
        if (!bsPopupView) return;
        var month = bsPopupView.month + delta;
        var year = bsPopupView.year;
        if (month < 1) { month = 12; year -= 1; }
        if (month > 12) { month = 1; year += 1; }
        bsPopupView = { year: year, month: month };
        renderBsPopup();
        if (bsPopupTarget) positionBsPopup(bsPopupTarget);
    }

    function installBsPopupHandlers() {
        if (installBsPopupHandlers.__done) return;
        installBsPopupHandlers.__done = true;

        document.addEventListener('click', function (e) {
            var popup = ensureBsPopup();
            if (popup.style.display === 'none') return;

            var dayEl = e.target.closest('.global-bs-day:not(.is-empty)');
            if (dayEl && popup.contains(dayEl)) {
                selectBsDay(parseInt(dayEl.getAttribute('data-day'), 10));
                return;
            }

            var navEl = e.target.closest('.global-bs-nav');
            if (navEl && popup.contains(navEl)) {
                shiftBsMonth(parseInt(navEl.getAttribute('data-nav'), 10));
                return;
            }

            var todayEl = e.target.closest('.global-bs-today');
            if (todayEl && popup.contains(todayEl)) {
                var today = parseYmd(currentBsDate());
                if (today) {
                    bsPopupView = { year: today.year, month: today.month };
                    renderBsPopup();
                }
                return;
            }

            if (popup.contains(e.target)) return;
            if (bsPopupTarget && e.target === bsPopupTarget) return;
            closeBsPopup();
        });

        document.addEventListener('change', function (e) {
            var popup = ensureBsPopup();
            if (popup.style.display === 'none' || !popup.contains(e.target)) return;
            if (e.target.classList.contains('global-bs-year-select') || e.target.classList.contains('global-bs-month-select')) {
                var y = parseInt(popup.querySelector('.global-bs-year-select').value, 10);
                var m = parseInt(popup.querySelector('.global-bs-month-select').value, 10);
                bsPopupView = { year: y, month: m };
                renderBsPopup();
            }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeBsPopup();
        });

        global.addEventListener('scroll', function () {
            if (bsPopupTarget && bsPopup && bsPopup.style.display !== 'none') {
                positionBsPopup(bsPopupTarget);
            }
        }, true);
    }

    function bindBsPicker(input) {
        if (input.getAttribute('data-nepali-bound') === '1') return;
        input.setAttribute('data-nepali-bound', '1');

        installBsPopupHandlers();

        // Seed a valid value up front so forms always submit a real date even
        // if the user never opens the picker. Skip for fields explicitly marked
        // as optional (data-no-autoseed) - e.g. "leave blank to auto-calculate".
        if (!input.hasAttribute('data-no-autoseed')) {
            var seeded = seedBsValue(input);
            if (seeded && input.value !== seeded) {
                input.value = seeded;
                syncNepaliValue(input);
            }
        }

        input.addEventListener('focus', function () { openBsPopup(input); });
        input.addEventListener('click', function () { openBsPopup(input); });
        input.addEventListener('blur', function () {
            // Let click-selection inside the popup register before syncing typed text
            setTimeout(function () { syncNepaliValue(input); }, 150);
        });
    }

    function convertNativeDateToNepali(input) {
        if (input.getAttribute('data-global-date-converted') === '1') return input;

        var originalName = input.name || '';
        var originalValue = input.value || '';
        var hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = originalName;
        hidden.value = originalValue;
        hidden.className = 'global-date-hidden-ad';

        input.type = 'text';
        input.name = originalName ? originalName + '_np_display' : '';
        input.placeholder = input.placeholder || 'YYYY-MM-DD (BS)';
        input.autocomplete = 'off';
        input.setAttribute('data-global-date-converted', '1');
        input.setAttribute('data-global-original-name', originalName);
        input.__globalDateHidden = hidden;

        if (originalValue) {
            input.value = ad2bs(originalValue) || originalValue;
        }

        input.insertAdjacentElement('afterend', hidden);
        return input;
    }

    function initNepaliInput(input) {
        if (input.disabled || isHidden(input)) return;

        ensureClass(input);
        destroyFlatpickr(input);

        if (input.type === 'date') {
            input = convertNativeDateToNepali(input);
        } else {
            input.type = 'text';
            input.autocomplete = 'off';
        }

        input.classList.add('nepali-date-field');
        if (!input.placeholder) input.placeholder = 'YYYY-MM-DD (BS)';
        ensureWrapper(input);

        if (input.getAttribute(INIT_ATTR) === '1' && input.getAttribute(MODE_ATTR) === 'nepali') {
            return;
        }

        bindBsPicker(input);
        input.setAttribute(INIT_ATTR, '1');
        input.setAttribute(MODE_ATTR, 'nepali');
    }

    function initEnglishInput(input) {
        if (input.disabled || isHidden(input)) return;

        ensureClass(input);
        input.classList.remove('nepali-date-field');
        input.setAttribute(MODE_ATTR, 'english');
        input.setAttribute(INIT_ATTR, '1');

        // Native `type="date"` inputs render inconsistent browser-default chrome
        // (varies by OS/browser, no premium styling possible). Convert every one
        // to a flatpickr-enhanced text input - the same treatment Daily Report's
        // AD field already used - so the AD calendar looks and behaves the same
        // everywhere. The ISO value (YYYY-MM-DD) carries over unchanged.
        if (input.type === 'date') {
            input.type = 'text';
        }

        input.autocomplete = 'off';
        ensureWrapper(input);
        if (global.flatpickr && !input._flatpickr) {
            try {
                global.flatpickr(input, {
                    dateFormat: 'Y-m-d',
                    allowInput: true,
                    disableMobile: true
                });
            } catch (err) {}
        }
    }

    function initGlobalDatePickers(scope) {
        if (isInitializing) return;
        isInitializing = true;

        try {
            var root = scope && scope.querySelectorAll ? scope : document;
            var mode = normalizedMode();

            root.querySelectorAll(candidateSelector()).forEach(function (input) {
                if (!(input instanceof HTMLInputElement)) return;
                if (mode === 'nepali') {
                    initNepaliInput(input);
                } else {
                    initEnglishInput(input);
                }
            });
        } finally {
            isInitializing = false;
        }
    }

    function debounceInit(scope) {
        clearTimeout(mutationTimer);
        mutationTimer = setTimeout(function () {
            initGlobalDatePickers(scope || document);
        }, 80);
    }

    function hookDynamicContent() {
        document.addEventListener('shown.bs.modal', function (event) {
            initGlobalDatePickers(event.target);
        });

        document.body.addEventListener('htmx:afterSwap', function (event) {
            initGlobalDatePickers(event.detail && event.detail.target ? event.detail.target : document);
        });
        document.body.addEventListener('htmx:afterSettle', function (event) {
            initGlobalDatePickers(event.detail && event.detail.target ? event.detail.target : document);
        });

        document.addEventListener('formset:added', function (event) {
            initGlobalDatePickers(event.target);
        });
        document.addEventListener('datepickers:refresh', function (event) {
            initGlobalDatePickers(event.target && event.target.querySelectorAll ? event.target : document);
        });

        if (global.jQuery) {
            global.jQuery(document).ajaxComplete(function () {
                initGlobalDatePickers(document);
            });
        }

        if (global.MutationObserver) {
            new MutationObserver(function (mutations) {
                if (isInitializing) return;

                for (var i = 0; i < mutations.length; i += 1) {
                    if (mutations[i].addedNodes && mutations[i].addedNodes.length) {
                        debounceInit(document);
                        break;
                    }
                }
            }).observe(document.body, { childList: true, subtree: true });
        }
    }

    global.initGlobalDatePickers = initGlobalDatePickers;
    global.NepaliDate = {
        init: initGlobalDatePickers,
        bs2ad: bs2ad,
        ad2bs: ad2bs,
        // Object-shaped variants (JS Date <-> {year, month, day}) for pages
        // that build their own BS calendar grid (e.g. templates/admin/calendar.html)
        // instead of just needing YYYY-MM-DD strings - these expose the same
        // single BS_MONTH_DATA table as bs2ad/ad2bs so every page's BS<->AD
        // math (and weekday alignment) stays consistent app-wide.
        toAdDate: bsToAdDate,
        toBs: adDateToBs,
        monthLength: function (year, month) { return bsMonthLengths(year)[month - 1]; }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initGlobalDatePickers(document);
            hookDynamicContent();
        });
    } else {
        initGlobalDatePickers(document);
        hookDynamicContent();
    }

}(window, document));
