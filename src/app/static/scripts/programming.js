(function () {
    const context = window.PROGRAMMING_CONTEXT || {};
    const SCRIPTS_ENDPOINT = (plcId, scriptId = null) => {
        const base = `/api/plcs/${encodeURIComponent(plcId)}/scripts`;
        return scriptId ? `${base}/${encodeURIComponent(scriptId)}` : base;
    };

    let monacoEditorInstance = null;
    let currentScripts = [];
    let scriptLanguages = {};
    let selectedScriptId = null;

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function monacoLanguageFor(language) {
        const key = (language || '').toLowerCase();
        if (key === 'python') return 'python';
        if (key === 'st') return 'pascal';
        if (key === 'ladder') return 'plaintext';
        return key || 'plaintext';
    }

    function showScriptStatus(message, type = 'info', element) {
        const statusEl = element || document.getElementById('script-status');
        if (!statusEl) return;
        statusEl.textContent = message || '';
        statusEl.dataset.state = type;
    }

    function populateLanguageOptions(select, languages) {
        if (!select) return;
        const entries = Object.entries(languages || {});
        const previous = select.value;
        select.innerHTML = '';
        if (!entries.length) {
            const option = document.createElement('option');
            option.value = 'python';
            option.textContent = 'Python';
            select.appendChild(option);
            select.value = 'python';
            return;
        }
        entries.forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        });
        if (entries.some(([value]) => value === previous)) {
            select.value = previous;
        }
    }

    function renderScriptList(scripts, languages, container) {
        const list = container || document.getElementById('script-list');
        if (!list) return;
        list.innerHTML = '';
        if (!scripts || !scripts.length) {
            const empty = document.createElement('li');
            empty.className = 'script-empty';
            empty.textContent = 'Nenhum script cadastrado.';
            list.appendChild(empty);
            return;
        }
        scripts.forEach((script) => {
            const item = document.createElement('li');
            item.dataset.scriptId = script.id;

            const selectBtn = document.createElement('button');
            selectBtn.type = 'button';
            selectBtn.className = 'script-select';
            selectBtn.textContent = script.name;

            const lang = document.createElement('span');
            lang.className = 'script-language';
            lang.textContent = (languages && languages[script.language]) || script.language;

            const deleteBtn = document.createElement('button');
            deleteBtn.type = 'button';
            deleteBtn.className = 'script-delete';
            deleteBtn.innerHTML = '&times;';
            deleteBtn.setAttribute('aria-label', `Excluir script ${script.name}`);

            item.appendChild(selectBtn);
            item.appendChild(lang);
            item.appendChild(deleteBtn);
            list.appendChild(item);
        });
    }

    function highlightSelectedScript(scriptId) {
        const list = document.getElementById('script-list');
        if (!list) return;
        list.querySelectorAll('li').forEach((item) => {
            const current = Number(item.dataset.scriptId);
            item.classList.toggle('active', scriptId != null && current === scriptId);
        });
    }

    async function loadScripts(plcId, languageSelect, listContainer, statusEl, nameInput) {
        if (!plcId) return;
        try {
            const response = await fetch(SCRIPTS_ENDPOINT(plcId), { credentials: 'same-origin' });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || 'Erro ao carregar scripts.');
            }
            scriptLanguages = payload.languages || {};
            currentScripts = payload.scripts || [];
            populateLanguageOptions(languageSelect, scriptLanguages);
            renderScriptList(currentScripts, scriptLanguages, listContainer);
            if (selectedScriptId && !currentScripts.some((script) => script.id === selectedScriptId)) {
                selectedScriptId = null;
            }
            if (!selectedScriptId && currentScripts.length) {
                const first = currentScripts[0];
                selectedScriptId = first.id;
                if (nameInput) nameInput.value = first.name || '';
                if (languageSelect) {
                    languageSelect.value = first.language;
                }
                if (monacoEditorInstance) {
                    const lang = monacoLanguageFor(first.language);
                    monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
                    monacoEditorInstance.setValue(first.content || '');
                }
            }
            highlightSelectedScript(selectedScriptId);
            if (!currentScripts.length) {
                showScriptStatus('Nenhum script cadastrado até o momento.', 'info', statusEl);
            }
        } catch (error) {
            console.error(error);
            showScriptStatus(error.message || 'Erro ao carregar scripts.', 'error', statusEl);
        }
    }

    async function saveCurrentScript(plcId, nameInput, languageSelect, statusEl) {
        if (!monacoEditorInstance || !plcId) return;
        const name = nameInput?.value.trim();
        const language = languageSelect?.value || 'python';
        const content = monacoEditorInstance.getValue();
        if (!name) {
            showScriptStatus('Informe o nome do script.', 'error', statusEl);
            return;
        }
        if (!content.trim()) {
            showScriptStatus('O conteúdo do script está vazio.', 'error', statusEl);
            return;
        }
        try {
            const response = await fetch(SCRIPTS_ENDPOINT(plcId), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ name, language, content }),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || 'Erro ao guardar script.');
            }
            selectedScriptId = payload.id;
            showScriptStatus(`Script "${payload.name}" guardado com sucesso.`, 'success', statusEl);
            await loadScripts(plcId, languageSelect, document.getElementById('script-list'), statusEl, nameInput);
            highlightSelectedScript(selectedScriptId);
        } catch (error) {
            console.error(error);
            showScriptStatus(error.message || 'Erro ao guardar script.', 'error', statusEl);
        }
    }

    async function deleteScript(plcId, scriptId, statusEl) {
        if (!plcId || !scriptId) return;
        try {
            const response = await fetch(SCRIPTS_ENDPOINT(plcId, scriptId), {
                method: 'DELETE',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.message || 'Erro ao remover script.');
            }
            if (selectedScriptId === scriptId) {
                selectedScriptId = null;
                if (monacoEditorInstance) {
                    monacoEditorInstance.setValue('');
                }
            }
            showScriptStatus('Script removido com sucesso.', 'success', statusEl);
            await loadScripts(
                plcId,
                document.getElementById('script-language'),
                document.getElementById('script-list'),
                statusEl,
                document.getElementById('script-name')
            );
            highlightSelectedScript(selectedScriptId);
        } catch (error) {
            console.error(error);
            showScriptStatus(error.message || 'Erro ao remover script.', 'error', statusEl);
        }
    }

    function initProgrammingTabs() {
        const tabs = document.querySelectorAll('.programming-tab');
        const panels = document.querySelectorAll('.programming-panel');
        if (!tabs.length || !panels.length) return;

        const activate = (target) => {
            tabs.forEach((tab) => {
                tab.classList.toggle('active', tab.dataset.programmingTab === target);
            });
            panels.forEach((panel) => {
                panel.classList.toggle('active', panel.dataset.programmingPanel === target);
            });
            if (target === 'editor') {
                setTimeout(() => {
                    if (monacoEditorInstance) {
                        monacoEditorInstance.layout();
                    }
                }, 50);
            }
        };

        tabs.forEach((tab) => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.programmingTab;
                if (target) {
                    activate(target);
                }
            });
        });

        const initial = Array.from(tabs).find((tab) => tab.classList.contains('active'))?.dataset.programmingTab || 'docs';
        activate(initial);
    }

    function initScriptEditor() {
        const container = document.getElementById('script-editor');
        if (!container) return;

        const statusEl = document.getElementById('script-status');
        const nameInput = document.getElementById('script-name');
        const languageSelect = document.getElementById('script-language');
        const saveButton = document.getElementById('script-save');
        const listContainer = document.getElementById('script-list');

        const rawId = Number(container.dataset.plcId);
        const plcId = Number.isFinite(rawId) && rawId > 0 ? rawId : Number(context.plcId || 0);

        if (!plcId) {
            showScriptStatus('Selecione um CLP para iniciar a edição.', 'info', statusEl);
            if (saveButton) saveButton.disabled = true;
            if (languageSelect) languageSelect.disabled = true;
            if (nameInput) nameInput.disabled = true;
            return;
        }

        if (saveButton) saveButton.disabled = false;
        if (languageSelect) languageSelect.disabled = false;
        if (nameInput) nameInput.disabled = false;

        container.dataset.plcId = String(plcId);

        if (typeof window.require === 'undefined') {
            console.error('Monaco loader não encontrado.');
            showScriptStatus('Não foi possível carregar o editor de código.', 'error', statusEl);
            return;
        }

        window.require.config({
            paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' }
        });
        window.MonacoEnvironment = {
            getWorkerUrl() {
                const proxy = "self.MonacoEnvironment={baseUrl:'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/'};" +
                    "importScripts('https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/base/worker/workerMain.js');";
                return `data:text/javascript;charset=utf-8,${encodeURIComponent(proxy)}`;
            }
        };

        window.require(['vs/editor/editor.main'], () => {
            monacoEditorInstance = monaco.editor.create(container, {
                value: '',
                language: monacoLanguageFor(languageSelect?.value || 'python'),
                theme: 'vs-dark',
                automaticLayout: true,
                minimap: { enabled: false },
            });

            loadScripts(plcId, languageSelect, listContainer, statusEl, nameInput);

            if (saveButton) {
                saveButton.addEventListener('click', () => {
                    saveCurrentScript(plcId, nameInput, languageSelect, statusEl);
                });
            }

            if (languageSelect) {
                languageSelect.addEventListener('change', () => {
                    if (!monacoEditorInstance) return;
                    const lang = monacoLanguageFor(languageSelect.value);
                    monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
                });
            }

            if (listContainer) {
                listContainer.addEventListener('click', (event) => {
                    const target = event.target;
                    const item = target.closest('li');
                    if (!item) return;
                    const scriptId = Number(item.dataset.scriptId);
                    if (target.classList.contains('script-delete')) {
                        if (scriptId) {
                            deleteScript(plcId, scriptId, statusEl);
                        }
                        return;
                    }
                    if (target.classList.contains('script-select') && scriptId) {
                        const script = currentScripts.find((entry) => entry.id === scriptId);
                        if (!script) return;
                        selectedScriptId = script.id;
                        highlightSelectedScript(script.id);
                        if (nameInput) nameInput.value = script.name || '';
                        if (languageSelect) {
                            languageSelect.value = script.language;
                            const lang = monacoLanguageFor(script.language);
                            monaco.editor.setModelLanguage(monacoEditorInstance.getModel(), lang);
                        }
                        if (monacoEditorInstance) {
                            monacoEditorInstance.setValue(script.content || '');
                            monacoEditorInstance.focus();
                        }
                        showScriptStatus(`Script "${script.name}" carregado.`, 'info', statusEl);
                    }
                });
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        initProgrammingTabs();
        initScriptEditor();
    });
})();
