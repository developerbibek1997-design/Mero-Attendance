/*
 * Mero Attendance global calendar system.
 * The organization setting controls every date input:
 *   window.ORG_DATE_TYPE = "nepali" -> BS picker with AD hidden value when needed
 *   anything else / missing        -> English YYYY-MM-DD picker
 */
(function (global, document) {
    'use strict';

    var INIT_ATTR = 'data-global-date-picker-init';
    var MODE_ATTR = 'data-global-date-picker-mode';
    var WARNING_KEY = '__meroDatePickerWarned';
    var mutationTimer = null;

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

    function bs2ad(bsValue) {
        var parsed = parseYmd(bsValue);
        if (!parsed || typeof global.NepaliFunctions === 'undefined') return '';
        try {
            return asYmd(global.NepaliFunctions.BS2AD(parsed));
        } catch (err) {
            return '';
        }
    }

    function ad2bs(adValue) {
        var parsed = parseYmd(adValue);
        if (!parsed || typeof global.NepaliFunctions === 'undefined') return '';
        try {
            return asYmd(global.NepaliFunctions.AD2BS(parsed));
        } catch (err) {
            return '';
        }
    }

    function currentBsDate() {
        if (typeof global.NepaliFunctions === 'undefined' || !global.NepaliFunctions.GetCurrentBsDate) {
            return '';
        }
        try {
            return asYmd(global.NepaliFunctions.GetCurrentBsDate());
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
        var bsValue = String(input.value || '').trim();
        input.value = bsValue;
        var hidden = input.__globalDateHidden || pairedHiddenInput(input);
        if (hidden) {
            hidden.value = bsValue ? (bs2ad(bsValue) || hidden.value || bsValue) : '';
            dispatchNative(hidden);
        }
        dispatchNative(input);
    }

    function destroyFlatpickr(input) {
        if (input && input._flatpickr && typeof input._flatpickr.destroy === 'function') {
            try { input._flatpickr.destroy(); } catch (err) {}
        }
    }

    function installNepaliPluginGuard() {
        var $ = global.jQuery || global.$;
        if (!$ || !$.fn || !$.fn.nepaliDatePicker || $.fn.nepaliDatePicker.__globalGuarded) return;

        var original = $.fn.nepaliDatePicker;
        var guarded = function (options) {
            if (typeof options === 'string') {
                return original.apply(this, arguments);
            }
            return this.each(function () {
                if (this.getAttribute('data-nepali-plugin-ready') === '1') return;
                original.call($(this), options || {});
                this.setAttribute('data-nepali-plugin-ready', '1');
            });
        };
        guarded.__globalGuarded = true;
        guarded.__original = original;
        $.fn.nepaliDatePicker = guarded;
    }

    function bindNepaliPicker(input) {
        var $ = global.jQuery || global.$;
        if (!$ || !$.fn || !$.fn.nepaliDatePicker) {
            warnOnce('Nepali date picker library is not loaded; falling back to the existing date input.');
            return false;
        }

        installNepaliPluginGuard();

        try {
            $(input)
                .off('change.globalDatePicker input.globalDatePicker dateSelect.globalDatePicker')
                .on('change.globalDatePicker input.globalDatePicker dateSelect.globalDatePicker', function () {
                    syncNepaliValue(input);
                })
                .nepaliDatePicker({
                    dateFormat: 'YYYY-MM-DD',
                    closeOnDateSelect: true,
                    ndpYear: true,
                    ndpMonth: true,
                    ndpYearCount: 15,
                    onChange: function () {
                        syncNepaliValue(input);
                    },
                    onSelect: function () {
                        syncNepaliValue(input);
                    }
                });
        } catch (err) {
            warnOnce('Nepali date picker could not be initialized on one or more inputs.');
            return false;
        }
        return true;
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

        if (bindNepaliPicker(input)) {
            input.setAttribute(INIT_ATTR, '1');
            input.setAttribute(MODE_ATTR, 'nepali');
            if (!input.value && input.id === 'force-nepali-cal') {
                input.value = currentBsDate();
            }
            if (input.value) syncNepaliValue(input);
        }
    }

    function initEnglishInput(input) {
        if (input.disabled || isHidden(input)) return;

        ensureClass(input);
        input.classList.remove('nepali-date-field');
        input.setAttribute(MODE_ATTR, 'english');
        input.setAttribute(INIT_ATTR, '1');

        if (input.id === 'english-datepicker' || input.type !== 'date') {
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
        } else {
            ensureWrapper(input);
        }
    }

    function initGlobalDatePickers(scope) {
        var root = scope && scope.querySelectorAll ? scope : document;
        var mode = normalizedMode();
        if (mode === 'nepali') installNepaliPluginGuard();

        root.querySelectorAll(candidateSelector()).forEach(function (input) {
            if (!(input instanceof HTMLInputElement)) return;
            if (mode === 'nepali') {
                initNepaliInput(input);
            } else {
                initEnglishInput(input);
            }
        });
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
        ad2bs: ad2bs
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
