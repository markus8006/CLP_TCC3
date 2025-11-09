(function () {
    function activateTab(container, target) {
        const buttons = Array.from(container.querySelectorAll('[data-view-target]'));
        const panels = Array.from(container.querySelectorAll('[data-view]'));
        buttons.forEach((button) => {
            const isActive = button.dataset.viewTarget === target;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', String(isActive));
        });
        panels.forEach((panel) => {
            const isActive = panel.dataset.view === target;
            panel.classList.toggle('active', isActive);
            panel.toggleAttribute('hidden', !isActive);
            panel.setAttribute('aria-hidden', String(!isActive));
        });
    }

    function initTabs(root) {
        const containers = root.querySelectorAll('[data-management-tabs]');
        containers.forEach((container) => {
            const buttons = Array.from(container.querySelectorAll('[data-view-target]'));
            if (!buttons.length) {
                return;
            }
            const defaultTarget = (buttons.find((btn) => btn.classList.contains('active')) || buttons[0]).dataset.viewTarget;
            activateTab(container, defaultTarget);

            buttons.forEach((button) => {
                button.addEventListener('click', () => {
                    const target = button.dataset.viewTarget;
                    if (!target) {
                        return;
                    }
                    activateTab(container, target);
                });
            });
        });
    }

    function initFilters(root) {
        const filters = root.querySelectorAll('[data-table-filter]');
        filters.forEach((input) => {
            const selector = input.dataset.tableFilter;
            if (!selector) {
                return;
            }
            const table = root.querySelector(selector);
            if (!table) {
                return;
            }
            const getRows = () => {
                const body = table.tBodies[0];
                return body ? Array.from(body.rows) : [];
            };
            input.addEventListener('input', () => {
                const query = input.value.trim().toLowerCase();
                getRows().forEach((row) => {
                    if (!query) {
                        row.hidden = false;
                        return;
                    }
                    const content = row.textContent.toLowerCase();
                    row.hidden = !content.includes(query);
                });
            });
        });
    }

    function initStepNavigation(root) {
        const navigations = root.querySelectorAll('[data-step-nav]');
        navigations.forEach((nav) => {
            const form = nav.closest('form');
            if (!form) {
                return;
            }
            const steps = Array.from(form.querySelectorAll('.form-step[data-step]'));
            if (!steps.length) {
                return;
            }

            let currentIndex = steps.findIndex((step) => step.classList.contains('active'));
            if (currentIndex === -1) {
                currentIndex = 0;
            }

            const prevButton = nav.querySelector('[data-step-action="prev"]');
            const nextButton = nav.querySelector('[data-step-action="next"]');

            function setActiveStep(index) {
                steps.forEach((step, stepIndex) => {
                    step.classList.toggle('active', stepIndex === index);
                });

                if (prevButton) {
                    prevButton.disabled = index === 0;
                }

                if (nextButton) {
                    nextButton.disabled = index === steps.length - 1;
                }
            }

            setActiveStep(currentIndex);

            nav.addEventListener('click', (event) => {
                const button = event.target.closest('[data-step-action]');
                if (!button) {
                    return;
                }

                event.preventDefault();
                const { stepAction } = button.dataset;

                if (stepAction === 'next' && currentIndex < steps.length - 1) {
                    currentIndex += 1;
                    setActiveStep(currentIndex);
                } else if (stepAction === 'prev' && currentIndex > 0) {
                    currentIndex -= 1;
                    setActiveStep(currentIndex);
                }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        const root = document.body || document.documentElement;
        initTabs(root);
        initFilters(root);
        initStepNavigation(root);
    });
})();
