document.addEventListener('DOMContentLoaded', function() {

    // --- LOAD & DISPLAY PROCESS LOG SUMMARIES ---
    function loadProcessLogSummary() {
        fetch('/api/last-process-log-json')
            .then(response => response.json())
            .then(data => {
                // Display in all tabs
                const tabs = ['Sales', 'Advances', 'Banking', 'Final'];
                tabs.forEach(tab => {
                    const boxId = `log-summary-${tab.toLowerCase()}`;
                    const box = document.getElementById(boxId);
                    if (!box) return;

                    if (!data.available) {
                        box.style.display = 'none';
                        return;
                    }

                    // Show the box
                    box.style.display = 'block';

                    if (data.has_errors) {
                        // Show error summary
                        box.innerHTML = `
                            <div style="background: #ffe5e5; border-left: 4px solid #dc3545; padding: 15px; border-radius: 5px;">
                                <h4 style="color: #dc3545; margin: 0 0 10px 0;">⚠️ Error Detected in Last Process</h4>
                                <p style="margin: 0 0 10px 0; font-size: 0.9rem; color: #555;">
                                    The last process encountered errors. Click the button below to see details and fix the issue.
                                </p>
                                <a href="/last-process-log" target="_blank" class="btn-process" 
                                   style="background: #dc3545; color: white; padding: 8px 12px; border-radius: 4px; 
                                           text-decoration: none; font-size: 0.9rem; display: inline-block;">
                                    📋 View Full Error Details
                                </a>
                            </div>
                        `;
                    } else {
                        // Show success
                        box.innerHTML = `
                            <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 15px; border-radius: 5px;">
                                <h4 style="color: #28a745; margin: 0 0 5px 0;">✅ Last Process Completed Successfully</h4>
                                <p style="margin: 0; font-size: 0.9rem; color: #155724;">No errors detected. You can proceed to the next step.</p>
                            </div>
                        `;
                    }
                });
            })
            .catch(err => console.error('Failed to load process log:', err));
    }

    // Load logs on page load
    loadProcessLogSummary();

    // --- TAB SWITCHING LOGIC ---
    window.openTab = function(evt, tabName) {
        let tabContents = document.getElementsByClassName("tab-content");
        for (let i = 0; i < tabContents.length; i++) {
            tabContents[i].style.display = "none";
        }

        let tabButtons = document.getElementsByClassName("tab-button");
        for (let i = 0; i < tabButtons.length; i++) {
            tabButtons[i].className = tabButtons[i].className.replace(" active", "");
        }

        document.getElementById(tabName).style.display = "block";
        
        for (let i = 0; i < tabButtons.length; i++) {
            if (tabButtons[i].innerHTML.includes(tabName)) {
                tabButtons[i].className += " active";
            }
        }
        localStorage.setItem('mainAppActiveTab', tabName);
    }
    
    function setActiveTabOnLoad() {
        const storedTab = localStorage.getItem('mainAppActiveTab');
        const tabToLoad = storedTab || 'Sales'; 
        
        let foundButton = false;
        let tabButtons = document.getElementsByClassName("tab-button");
        for (let i = 0; i < tabButtons.length; i++) {
            if (tabButtons[i].innerHTML.includes(tabToLoad)) {
                tabButtons[i].click();
                foundButton = true;
                break;
            }
        }
        if (!foundButton && tabButtons.length > 0) {
            tabButtons[0].click();
        }
    }

    // --- PROGRESS BAR LOGIC ---
    const progressOverlay = document.getElementById('progress-overlay');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    let progressInterval;

    function startProgress() {
        if (progressOverlay) {
            progressOverlay.style.display = 'flex';
            progressBar.style.width = '0%';
            progressText.innerText = 'Starting... 0%';
            
            let width = 0;
            progressInterval = setInterval(() => {
                if (width >= 90) {
                    clearInterval(progressInterval);
                } else {
                    const increment = Math.max(1, (90 - width) / 10); 
                    width += increment;
                    progressBar.style.width = width + '%';
                    progressText.innerText = 'Processing... ' + Math.round(width) + '%';
                }
            }, 200);
        }
    }

    function finishProgress() {
        if (progressOverlay) {
            clearInterval(progressInterval);
            progressBar.style.width = '100%';
            progressText.innerText = 'Complete! Downloading...';
            setTimeout(() => {
                progressOverlay.style.display = 'none';
                progressBar.style.width = '0%';
            }, 1000); 
        }
    }

    function stopProgressError() {
        if (progressOverlay) {
            clearInterval(progressInterval);
            progressOverlay.style.display = 'none';
        }
    }

    // --- BANKING TAB DYNAMIC UI LOGIC ---
    const bankDropdown = document.getElementById("bank-select-dropdown");
    const addBankBtn = document.getElementById("add-bank-btn");
    const uploadsContainer = document.getElementById("bank-uploads-container");

    if (addBankBtn) {
        addBankBtn.addEventListener("click", function() {
            const selectedBankName = bankDropdown.options[bankDropdown.selectedIndex].text;
            const selectedBankValue = bankDropdown.value;

            if (!selectedBankValue) {
                alert("Please select a bank from the dropdown first.");
                return;
            }
            if (document.getElementById("bank-box-" + selectedBankValue)) {
                alert(selectedBankName + " has already been added.");
                return;
            }

            const newBankBox = document.createElement("div");
            newBankBox.className = "bank-upload-box";
            newBankBox.id = "bank-box-" + selectedBankValue; 
            
            newBankBox.innerHTML = `
                <button class="remove-bank-btn" title="Remove">&times;</button>
                <h3>🏦 ${selectedBankName}</h3>
                <div class="bank-upload-box-inputs">
                    <div class="file-group">
                        <label class="bank-input-label">📄 Transaction File <span class="required-mark">*</span></label>
                        <input type="file" name="file_${selectedBankValue}" class="file-input" accept=".xls,.xlsx,.xlsm,.csv" style="margin:0; width:100%;">
                        <small style="color: #888; font-size: 12px;">Supported: XLS, XLSX, XLSM, CSV</small>
                    </div>
                    <div class="date-group-container">
                        <label class="bank-input-label">📅 Date Range <span class="required-mark">*</span></label>
                        <div class="date-inputs-row">
                            <input type="text" name="date_from_${selectedBankValue}" class="date-input-flatpickr date-input" placeholder="DD-MM-YYYY" style="margin:0;">
                            <span class="separator">→</span>
                            <input type="text" name="date_to_${selectedBankValue}" class="date-input-flatpickr date-input" placeholder="DD-MM-YYYY" style="margin:0;">
                        </div>
                    </div>
                </div>
            `;
            uploadsContainer.appendChild(newBankBox);

            const dateInputs = newBankBox.querySelectorAll('.date-input-flatpickr');
            if (window.flatpickr) {
                flatpickr(dateInputs, {
                    dateFormat: "d-m-Y",
                    allowInput: true
                });
            }

            newBankBox.querySelector(".remove-bank-btn").addEventListener("click", function() {
                uploadsContainer.removeChild(newBankBox);
            });
            bankDropdown.selectedIndex = 0;
        });
    }

    // --- SALES PROCESSING (TAB 1) ---
    const salesButton = document.getElementById('btn-process-sales');
    const salesFile = document.getElementById('file-sales');
    if (salesButton) {
        salesButton.addEventListener('click', function() {
            const file = salesFile.files[0];
            if (!file) {
                alert('Please select a Sales file to process.');
                return;
            }
            const formData = new FormData();
            formData.append('sales_file', file);
            
            startProgress(); 

            fetch('/process-sales', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress(); 
                loadProcessLogSummary(); // Reload log summaries
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Processed_Sales.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                loadProcessLogSummary(); // Reload log summaries to show error
                alert('Error: ' + error.message);
            });
        });
    }

    // --- ADVANCES PROCESSING (TAB 2) ---
    const advancesButton = document.getElementById('btn-process-advances');
    const advancesFile = document.getElementById('file-advances');
    if (advancesButton) {
        advancesButton.addEventListener('click', function() {
            const file = advancesFile.files[0];
            if (!file) {
                alert('Please select an Advances file to process.');
                return;
            }
            const formData = new FormData();
            formData.append('advances_file', file);
            
            startProgress(); 

            fetch('/process-advances', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress(); 
                loadProcessLogSummary(); // Reload log summaries
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Processed_Advances_Consolidated.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                loadProcessLogSummary(); // Reload log summaries to show error
                alert('Error: ' + error.message);
            });
        });
    }

    // --- BANKING PROCESSING (TAB 3) ---
    const bankingButton = document.getElementById('btn-process-banking');
    if (bankingButton) {
        bankingButton.addEventListener('click', function() {
            const formData = new FormData();
            const bankBoxes = document.querySelectorAll('.bank-upload-box');

            if (bankBoxes.length === 0) {
                alert('Please add at least one bank file to process.');
                return;
            }

            let missingData = false;
            let errorMessage = "";

            for (const box of bankBoxes) {
                const bankTitle = box.querySelector('h3').innerText; 
                const fileInput = box.querySelector(`input[name^="file_"]`);
                const dateInputs = box.querySelectorAll('.date-input-flatpickr');
                const fromInput = dateInputs[0];
                const toInput = dateInputs[1];

                if (fileInput.files.length === 0) {
                    missingData = true;
                    errorMessage = `Please select a file for ${bankTitle}.`;
                    break;
                }
                if (!fromInput.value.trim()) {
                    missingData = true;
                    errorMessage = `Please enter a 'From' date for ${bankTitle}.`;
                    break;
                }
                if (!toInput.value.trim()) {
                    missingData = true;
                    errorMessage = `Please enter a 'To' date for ${bankTitle}.`;
                    break;
                }

                const bankNameFromDropdown = fileInput.name.replace('file_', '');
                formData.append('bank_name', bankNameFromDropdown);
                formData.append('file_' + bankNameFromDropdown, fileInput.files[0]);
                formData.append('date_from_' + bankNameFromDropdown, fromInput.value);
                formData.append('date_to_' + bankNameFromDropdown, toInput.value);
            }

            if (missingData) {
                alert(errorMessage);
                return;
            }

            startProgress(); 

            fetch('/process-banking', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress(); 
                loadProcessLogSummary(); // Reload log summaries
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Processed_Collection.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                loadProcessLogSummary(); // Reload log summaries to show error
                alert('Error: ' + error.message);
            });
        });
    }
    
    // --- NEW: FINAL PROCESS (TAB 4) - INDIVIDUAL FILE PROCESSING ---
    const individualButton = document.getElementById('btn-process-individual');
    const combineFile = document.getElementById('file-combine-mis');
    const finalMisFile = document.getElementById('file-final-mis');
    
    if (individualButton) {
        individualButton.addEventListener('click', function() {
            if (combineFile.files.length === 0) {
                alert('Please select a Combine MIS file.');
                return;
            }
            if (!finalMisFile.files[0]) {
                alert('Please select the Final MIS file.');
                return;
            }
            
            // Process ONLY the first selected file
            const formData = new FormData();
            formData.append('combine_mis', combineFile.files[0]); // Only first file
            formData.append('final_mis', finalMisFile.files[0]);

            startProgress();
            
            fetch('/process-individual-combine', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                const fileName = combineFile.files[0].name.split('.')[0];
                a.download = `Updated_Final_MIS_${fileName}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                alert('Individual file processed successfully!');
            })
            .catch(error => {
                stopProgressError();
                alert('Error: ' + error.message);
            });
        });
    }
    
    // --- FINAL PROCESS (TAB 4) - COMBINED FILE PROCESSING ---
    const finalButton = document.getElementById('btn-process-final');
    
    if (finalButton) {
        finalButton.addEventListener('click', function() {
            if (combineFile.files.length === 0) {
                alert('Please select one or more Combine MIS file(s).');
                return;
            }
            if (!finalMisFile.files[0]) {
                alert('Please select the Final MIS file.');
                return;
            }

            const formData = new FormData();
            
            // Append multiple Combine MIS files
            for (let i = 0; i < combineFile.files.length; i++) {
                formData.append('combine_mis', combineFile.files[i]);
            }
            
            // Append single Final MIS file
            formData.append('final_mis', finalMisFile.files[0]);

            startProgress();
            
            fetch('/process-final-step', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Final_Consolidated_Report.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                alert('Error: ' + error.message);
            });
        });
    }
    
    // --- NEW HANDLERS FOR THREE-STEP WORKFLOW (STEP A, B, C) ---
    const combineOnlyButton = document.getElementById('btn-process-combine-only');
    const combineOnlyInput = document.getElementById('file-combine-mis-process');
    // inspection box helper for Combine-only input
    function showInspectionBox(inputElem, boxId, html) {
        let box = document.getElementById(boxId);
        if (!box) {
            box = document.createElement('div');
            box.id = boxId;
            box.className = 'inspection-box';
            inputElem.parentNode.insertBefore(box, inputElem.nextSibling);
        }
        box.innerHTML = html;
    }
    if (combineOnlyButton) {
        combineOnlyButton.addEventListener('click', function() {
            if (!combineOnlyInput || combineOnlyInput.files.length === 0) {
                alert('Please select one or more Combine MIS file(s) to process.');
                return;
            }

            const formData = new FormData();
            for (let i = 0; i < combineOnlyInput.files.length; i++) {
                formData.append('combine_mis', combineOnlyInput.files[i]);
            }

            startProgress();
            fetch('/process-combine-only', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress();
                loadProcessLogSummary(); // Reload log summaries
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Processed_Combine_MIS.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                loadProcessLogSummary(); // Reload log summaries to show error
                alert('Error: ' + error.message);
            });
        });
    }

    // Inspect Combine MIS on file select
    if (combineOnlyInput) {
        combineOnlyInput.addEventListener('change', function() {
            if (combineOnlyInput.files.length === 0) {
                showInspectionBox(combineOnlyInput, 'inspect-combine-box', 'No file selected.');
                return;
            }
            const file = combineOnlyInput.files[0];
            const formData = new FormData();
            formData.append('combine_mis', file);
            fetch('/inspect-combine-mis', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    showInspectionBox(combineOnlyInput, 'inspect-combine-box', `<b>Error:</b> ${data.error}`);
                    return;
                }
                const sheets = data.sheets || [];
                const cols = data.sheet_columns || {};
                const preferred = 'MIS Working';
                let html = `<b>Detected sheets:</b> ${sheets.join(', ')}<br>`;
                if (!data.preferred_present) {
                    html += `<div style="color:darkorange"><b>Warning:</b> Expected sheet '<i>${preferred}</i>' not found. Processing will try the first sheet.</div>`;
                } else {
                    html += `<div style="color:green">Found expected sheet '<i>${preferred}</i>'.</div>`;
                }
                // show columns for preferred or first sheet
                const showSheet = data.preferred_present ? preferred : sheets[0];
                if (showSheet && cols[showSheet]) {
                    html += `<b>Columns in '${showSheet}':</b> ${cols[showSheet].join(', ')}<br>`;
                }
                html += `<small>Processing will not change column names in your files.</small>`;
                showInspectionBox(combineOnlyInput, 'inspect-combine-box', html);
            })
            .catch(err => {
                showInspectionBox(combineOnlyInput, 'inspect-combine-box', `<b>Error:</b> ${err.message}`);
            });
        });
    }

    const finalOnlyButton = document.getElementById('btn-process-final-only');
    const finalOnlyInput = document.getElementById('file-final-mis-process');
    if (finalOnlyButton) {
        finalOnlyButton.addEventListener('click', function() {
            if (!finalOnlyInput || finalOnlyInput.files.length === 0) {
                alert('Please select the Final MIS file to process.');
                return;
            }

            const formData = new FormData();
            formData.append('final_mis', finalOnlyInput.files[0]);

            startProgress();
            fetch('/process-final-only', { method: 'POST', body: formData })
            .then(response => {
                if (response.ok) { return response.blob(); }
                return response.json().then(errorData => { throw new Error(errorData.error); });
            })
            .then(blob => {
                finishProgress();
                loadProcessLogSummary(); // Reload log summaries
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Processed_Final_MIS.xlsx';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                stopProgressError();
                loadProcessLogSummary(); // Reload log summaries to show error
                alert('Error: ' + error.message);
            });
        });
    }

    // Inspect Final MIS on file select
    if (finalOnlyInput) {
        finalOnlyInput.addEventListener('change', function() {
            if (finalOnlyInput.files.length === 0) {
                showInspectionBox(finalOnlyInput, 'inspect-final-box', 'No file selected.');
                return;
            }
            const file = finalOnlyInput.files[0];
            const formData = new FormData();
            formData.append('final_mis', file);
            fetch('/inspect-final-mis', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    showInspectionBox(finalOnlyInput, 'inspect-final-box', `<b>Error:</b> ${data.error}`);
                    return;
                }
                const sheets = data.sheets || [];
                const cols = data.sheet_columns || {};
                const preferred = 'Reconciliation by Date by Store';
                let html = `<b>Detected sheets:</b> ${sheets.join(', ')}<br>`;
                if (!data.preferred_present) {
                    html += `<div style="color:darkorange"><b>Warning:</b> Expected sheet '<i>${preferred}</i>' not found. Processing will try the first sheet.</div>`;
                } else {
                    html += `<div style="color:green">Found expected sheet '<i>${preferred}</i>'.</div>`;
                }
                const showSheet = data.preferred_present ? preferred : sheets[0];
                if (showSheet && cols[showSheet]) {
                    html += `<b>Columns in '${showSheet}':</b> ${cols[showSheet].join(', ')}<br>`;
                }
                html += `<div style="color:crimson"><b>Note:</b> The application will not modify column names in '<i>${preferred}</i>'. Only the specific update columns will be written.</div>`;
                showInspectionBox(finalOnlyInput, 'inspect-final-box', html);
            })
            .catch(err => {
                showInspectionBox(finalOnlyInput, 'inspect-final-box', `<b>Error:</b> ${err.message}`);
            });
        });
    }

    // Step C (merge) has been removed per workflow change
    
    // --- INITIALIZE THE PAGE ---
    setActiveTabOnLoad();

    // --- FETCH LAST PROCESS LOG SUMMARY AND SHOW PER-TAB NOTICES ---
    function fetchAndRenderLogSummary() {
        fetch('/api/last-log-summary')
        .then(r => r.json())
        .then(data => {
            if (!data || !data.found) return;
            const summary = data.summary || {};
            const errorCount = summary.error_count || 0;
            const warnCount = summary.warning_count || 0;

            function makeHtml(prefix) {
                let html = '';
                if (errorCount > 0) {
                    html += `<div style="background:#ffe6e6;border-left:4px solid #dc3545;padding:10px;border-radius:6px;margin-bottom:8px;color:#6b0000;"><b>${prefix}:</b> ${errorCount} error(s) found. <a href='/processing-log' target='_blank'>View details</a></div>`;
                } else if (warnCount > 0) {
                    html += `<div style="background:#fff8e1;border-left:4px solid #ff9800;padding:10px;border-radius:6px;margin-bottom:8px;color:#664d03;"><b>${prefix}:</b> ${warnCount} warning(s) found. <a href='/processing-log' target='_blank'>View details</a></div>`;
                } else {
                    html += `<div style="background:#edf7ed;border-left:4px solid #28a745;padding:10px;border-radius:6px;margin-bottom:8px;color:#1b5e20;"><b>${prefix}:</b> No recent errors. <a href='/processing-log' target='_blank'>View log</a></div>`;
                }
                return html;
            }

            const salesBox = document.getElementById('log-summary-sales');
            const advBox = document.getElementById('log-summary-advances');
            const bankBox = document.getElementById('log-summary-banking');
            const finalBox = document.getElementById('log-summary-final');

            if (salesBox) { salesBox.innerHTML = makeHtml('Sales'); salesBox.style.display = 'block'; }
            if (advBox) { advBox.innerHTML = makeHtml('Advances'); advBox.style.display = 'block'; }
            if (bankBox) { bankBox.innerHTML = makeHtml('Banking'); bankBox.style.display = 'block'; }
            if (finalBox) { finalBox.innerHTML = makeHtml('Final Process'); finalBox.style.display = 'block'; }
        })
        .catch(err => { /* silently fail; log not critical */ });
    }

    // Fetch right away to populate the UI
    fetchAndRenderLogSummary();

});