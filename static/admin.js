document.addEventListener('DOMContentLoaded', function() {

    // --- DATA LOAD ---
    let banksData = [], salesRuleData = {}, advanceRuleData = {}, outputColumns = {};
    try {
        const bankDataEl = document.getElementById('bank-data');
        const salesRuleDataEl = document.getElementById('sales-rule-data');
        const advanceRuleDataEl = document.getElementById('advance-rule-data');
        const outputColumnsEl = document.getElementById('output-cols-data');

        if (bankDataEl) banksData = JSON.parse(bankDataEl.textContent);
        if (salesRuleDataEl) salesRuleData = JSON.parse(salesRuleDataEl.textContent);
        if (advanceRuleDataEl) advanceRuleData = JSON.parse(advanceRuleDataEl.textContent);
        if (outputColumnsEl) outputColumns = JSON.parse(outputColumnsEl.textContent);
    } catch(e) {
        console.error("Error parsing initial JSON data:", e);
    }

    // --- ELEMENTS ---
    const modal = document.getElementById('ruleModal');
    const modalTitle = document.getElementById('modalTitle');
    const form = document.getElementById('ruleForm');
    const bankIdField = document.getElementById('bank_id');
    const bankNameField = document.getElementById('bank_name');
    const startRowField = document.getElementById('start_row');
    const sheetNameField = document.getElementById('sheet_name');
    const mappingsContainer = document.getElementById('mappings');
    const modalActiveTabField = document.getElementById('modal_active_tab');

    const bankNameWrapper = document.getElementById('bank-name-field-wrapper');
    const salesSpecialRules = document.getElementById('sales-special-rules');
    const advancesSpecialRules = document.getElementById('advances-special-rules');

    // --- STATE ---
    let currentActiveTab = window.activeTab || 'Sales';


    // --- HELPER: Excel Letters ---
    function excelColName(n) {
        let name = "";
        let i = n + 1; 
        while (i > 0) {
            let remainder = (i - 1) % 26;
            name = String.fromCharCode(65 + remainder) + name;
            i = Math.floor((i - 1) / 26);
        }
        return name;
    }

    // --- TABS ---
    window.openAdminTab = function(evt, tabName) {
        // Hide all contents
        const contents = document.querySelectorAll('.tab-content');
        contents.forEach(c => c.style.display = 'none');
        // Deactivate all buttons
        const buttons = document.querySelectorAll('.tab-button');
        buttons.forEach(b => {
            b.classList.remove('text-blue-600', 'border-blue-600', 'active');
            b.classList.add('text-gray-500', 'border-transparent');
        });

        // Show target
        const target = document.getElementById(tabName);
        if (target) target.style.display = 'block';

        // Activate button
        if (evt && evt.currentTarget) {
            evt.currentTarget.classList.remove('text-gray-500', 'border-transparent');
            evt.currentTarget.classList.add('text-blue-600', 'border-blue-600', 'active');
        }

        currentActiveTab = tabName;
        updateAllHiddenTabs(tabName);
        localStorage.setItem('adminActiveTab', tabName);
    }

    function setActiveTabOnLoad() {
        const urlTab = (window.activeTab && window.activeTab !== 'None') ? window.activeTab : null;
        const storedTab = localStorage.getItem('adminActiveTab');
        const tabToLoad = urlTab || storedTab || 'Sales';
        
        if (urlTab) localStorage.setItem('adminActiveTab', urlTab);

        const tabButton = document.querySelector(`.tab-button[data-tab="${tabToLoad}"]`);
        if (tabButton) {
            tabButton.click();
        } else {
            const first = document.querySelector('.tab-button');
            if(first) first.click();
        }
    }

    function updateAllHiddenTabs(tabName) {
        document.querySelectorAll('input[name="active_tab"]').forEach(input => input.value = tabName);
    }

    // --- MODAL ---
    window.closeModal = function() {
        if (modal) {
            modal.classList.add('hidden'); // Add hidden class to close
            // Reset logic is handled in openModal mostly, but good to clear id
            bankIdField.value = '';
        }
    }

    window.openModal = function(type, id = null) {
        console.log("Opening modal:", type, id);
        
        // 1. Reset Form UI
        form.reset();
        mappingsContainer.innerHTML = '';
        bankNameWrapper.classList.add('hidden');
        salesSpecialRules.classList.add('hidden');
        advancesSpecialRules.classList.add('hidden');

        // Set tab state for return redirect
        modalActiveTabField.value = currentActiveTab;

        let currentRule = {};
        let currentMappings = {};
        let currentOutputCols = [];

        // 2. Load Data based on Type
        try {
            if (type === 'sales') {
                modalTitle.textContent = 'Edit Sales Rule';
                form.action = '/admin/save_sales_rule';
                currentRule = salesRuleData;
                currentMappings = currentRule.mappings || {};
                currentOutputCols = JSON.parse(outputColumns.sales.json);
                
                salesSpecialRules.classList.remove('hidden');
                // Fill special fields
                document.getElementById('copy_col_source').value = currentRule.copy_col_source || '';
                document.getElementById('copy_col_dest').value = currentRule.copy_col_dest || '';
                document.getElementById('bp_remove_cols').value = currentRule.bp_remove_cols || '';
                document.getElementById('prefix_remove_col').value = currentRule.prefix_remove_col || '';
                document.getElementById('prefix_remove_values').value = currentRule.prefix_remove_values || '';

            } else if (type === 'advances') {
                modalTitle.textContent = 'Edit Advances Rule';
                form.action = '/admin/save_advance_rule';
                currentRule = advanceRuleData;
                currentMappings = currentRule.mappings || {};
                currentOutputCols = JSON.parse(outputColumns.advances.json);

                advancesSpecialRules.classList.remove('hidden');
                // Fill special fields
                document.getElementById('vlookup_source_col').value = currentRule.vlookup_source_col || '';
                document.getElementById('vlookup_sales_col').value = currentRule.vlookup_sales_col || '';
                document.getElementById('vlookup_dest_col').value = currentRule.vlookup_dest_col || '';
                document.getElementById('vlookup_value_col').value = currentRule.vlookup_value_col || '';

            } else if (type === 'new_bank') {
                modalTitle.textContent = 'Add New Bank Rule';
                form.action = '/admin/save_bank';
                bankIdField.value = 'new';
                currentRule = { start_row: 2, sheet_name: 'Sheet1' };
                currentMappings = {};
                currentOutputCols = JSON.parse(outputColumns.banking.json);
                
                bankNameWrapper.classList.remove('hidden');

            } else if (type === 'edit_bank') {
                modalTitle.textContent = 'Edit Bank Rule';
                form.action = '/admin/save_bank';
                bankIdField.value = id;
                currentRule = banksData.find(b => b.id.toString() === id.toString());
                
                if (!currentRule) {
                    alert('Error: Could not find bank data ID ' + id);
                    return;
                }
                currentMappings = currentRule.mappings || {};
                currentOutputCols = JSON.parse(outputColumns.banking.json);
                
                bankNameWrapper.classList.remove('hidden');
                bankNameField.value = currentRule.bank_name;
            }

            // 3. Fill Shared Fields
            startRowField.value = currentRule.start_row || 2;
            sheetNameField.value = currentRule.sheet_name || '';

            // 4. Generate Mapping Rows
            if (Array.isArray(currentOutputCols)) {
                currentOutputCols.forEach((col, index) => {
                    const savedValue = currentMappings[col] || '';
                    const row = createMappingRow(col, savedValue, index, type);
                    mappingsContainer.appendChild(row);
                });
            }

            // 5. Show Modal
            modal.classList.remove('hidden');

        } catch (err) {
            console.error("Error in openModal:", err);
            alert("An error occurred opening the form. Please check console.");
        }
    }

    function createMappingRow(outputCol, sourceColValue, index, type) {
        const div = document.createElement('div');
        // Tailwind grid layout for row
        div.className = 'grid grid-cols-12 gap-4 items-center';

        const label = document.createElement('label');
        label.className = 'col-span-5 text-right text-sm font-medium text-gray-600 break-words pr-2';
        label.htmlFor = `map_${outputCol}`;

        // Add (A), (B) logic ONLY for banking
        if (type === 'new_bank' || type === 'edit_bank') {
             const colLetter = excelColName(index);
             label.textContent = `(${colLetter}) ${outputCol}:`;
        } else {
             label.textContent = `${outputCol}:`;
        }
        
        const input = document.createElement('input');
        input.type = 'text';
        input.id = `map_${outputCol}`;
        input.name = `map_${outputCol}`;
        input.value = sourceColValue;
        input.className = 'col-span-7 mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm';
        input.placeholder = 'Source Column Name';

        div.appendChild(label);
        div.appendChild(input);
        return div;
    }

    // Close modal if clicking on the background
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
            }
        });
    }
    
    // --- EDIT/SAVE BUTTONS FOR COLUMNS ---
    function setupEditSaveButton(type) {
        const editBtn = document.getElementById(`edit-cols-${type}`);
        const saveBtn = document.getElementById(`save-cols-${type}`);
        const textarea = document.getElementById(`output-cols-${type}`);

        if (editBtn && saveBtn && textarea) {
            editBtn.addEventListener('click', () => {
                textarea.readOnly = false;
                textarea.classList.remove('bg-gray-50');
                textarea.classList.add('bg-white', 'border-blue-300');
                editBtn.classList.add('hidden');
                saveBtn.classList.remove('hidden');
            });
        }
    }

    setupEditSaveButton('sales');
    setupEditSaveButton('advances');
    setupEditSaveButton('banking');

    // --- INIT ---
    setActiveTabOnLoad();

});function deletePrompt(id) { if (!confirm('Are you sure?')) return; fetch('/api/prompts/' + id, {method: 'DELETE'}).then(r=>r.json()).then(d=>{ if(d.message==='Deleted') window.location.reload(); else alert('Error: ' + JSON.stringify(d)); }); }
