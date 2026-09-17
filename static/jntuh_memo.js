/**
 * static/jntuh_memo.js
 * Standardized Official JNTUH Consolidated Memo of Marks / Grades & Credits (CMM) Renderer
 * Provides authentic official memo paper view & mobile-responsive views across Student, Faculty, and Admin dashboards.
 */

(function (global) {
    'use strict';

    // Grade to Grade Point Mapping (JNTUH R18/R22 Regulations)
    function getGradePoint(gradeStr, passed) {
        if (!gradeStr) return passed ? 5 : 0;
        const g = String(gradeStr).trim().toUpperCase();
        if (g === 'O' || g === '10') return 10;
        if (g === 'A+' || g === '9') return 9;
        if (g === 'A' || g === '8') return 8;
        if (g === 'B+' || g === '7') return 7;
        if (g === 'B' || g === '6') return 6;
        if (g === 'C' || g === '5') return 5;
        if (g === 'F' || g === 'AB' || g === 'ABSENT' || g === '0' || !passed) return 0;
        return passed ? 6 : 0;
    }

    // Branch Full Name from Roll / Code
    function getBranchFullName(roll, dept) {
        const d = (dept || '').toUpperCase();
        if (d === 'CSE') return 'Computer Science & Engineering';
        if (d === 'CSD') return 'Computer Science & Engineering (Data Science)';
        if (d === 'CSM') return 'Computer Science & Engineering (AI & ML)';
        if (d === 'ECE') return 'Electronics & Communication Engineering';
        if (d === 'EEE') return 'Electrical & Electronics Engineering';
        if (d === 'MECH') return 'Mechanical Engineering';
        if (d === 'CIVIL') return 'Civil Engineering';

        const r = (roll || '').toUpperCase();
        if (r.includes('A05') || r.includes('1A05')) return 'Computer Science & Engineering';
        if (r.includes('A66') || r.includes('1A66')) return 'Computer Science & Engineering (Data Science)';
        if (r.includes('A67') || r.includes('1A67')) return 'Computer Science & Engineering (AI & ML)';
        if (r.includes('A04') || r.includes('1A04')) return 'Electronics & Communication Engineering';
        if (r.includes('A02') || r.includes('1A02')) return 'Electrical & Electronics Engineering';
        if (r.includes('A03') || r.includes('1A03')) return 'Mechanical Engineering';
        if (r.includes('A01') || r.includes('1A01')) return 'Civil Engineering';
        return 'Computer Science & Engineering';
    }

    function getCollegeName(roll) {
        return 'DRK College of Engineering and Technology';
    }

    function getCollegeCode(roll) {
        const r = (roll || '').toUpperCase();
        if (r.length >= 5) {
            return r.substring(2, 4); // e.g. 23U51A05A6 -> U5
        }
        return 'U5';
    }

    // Deduplicate & merge semester attempts to compute best attempt per subject
    function processSemestersData(results) {
        const semMap = {};
        (results || []).forEach(function (sem) {
            let semNum = parseInt(sem.semester, 10);
            if (isNaN(semNum)) {
                const match = String(sem.semester).match(/\d+/);
                semNum = match ? parseInt(match[0], 10) : 1;
            }
            const semKey = String(semNum);

            if (!semMap[semKey]) {
                semMap[semKey] = {
                    semester: semNum,
                    type: sem.type || 'Regular',
                    examCode: sem.examCode || '',
                    subjects: [],
                    _subjMap: {}
                };
            }

            const currentSem = semMap[semKey];
            (sem.subjects || []).forEach(function (sub) {
                const code = (sub.code || '').trim().toUpperCase();
                const name = (sub.name || '').trim().toUpperCase();
                const subKey = code || name;
                if (!subKey) return;

                const subPassed = sub.passed !== undefined ? Boolean(sub.passed) : (sub.grade && sub.grade !== 'F' && sub.grade !== 'AB');
                const subPts = sub.points !== undefined ? sub.points : getGradePoint(sub.grade, subPassed);
                const subCreds = parseFloat(sub.credits) || 0;

                const subjObj = {
                    code: code || '—',
                    name: name || 'SUBJECT',
                    grade: (sub.grade || (subPassed ? 'P' : 'F')).toUpperCase(),
                    points: subPts,
                    credits: subCreds,
                    passed: subPassed,
                    internal: sub.internal !== undefined ? sub.internal : '',
                    external: sub.external !== undefined ? sub.external : ''
                };

                if (!currentSem._subjMap[subKey]) {
                    currentSem._subjMap[subKey] = subjObj;
                } else {
                    const prev = currentSem._subjMap[subKey];
                    if (subjObj.passed && !prev.passed) {
                        currentSem._subjMap[subKey] = subjObj;
                    } else if (subjObj.passed === prev.passed) {
                        if (subjObj.points > prev.points) {
                            currentSem._subjMap[subKey] = subjObj;
                        }
                    }
                }
            });
        });

        const mergedResults = [];
        Object.keys(semMap).sort((a, b) => Number(a) - Number(b)).forEach(k => {
            const semObj = semMap[k];
            semObj.subjects = Object.values(semObj._subjMap);
            delete semObj._subjMap;

            let totalCreds = 0;
            let totalPts = 0;
            semObj.subjects.forEach(s => {
                if (s.credits > 0) {
                    totalCreds += s.credits;
                    totalPts += s.credits * s.points;
                }
            });
            semObj.sgpa = totalCreds > 0 ? (totalPts / totalCreds) : 0;
            semObj.totalCredits = totalCreds;
            mergedResults.push(semObj);
        });

        return mergedResults;
    }

    function getActiveBacklogs(processedSemesters) {
        const backlogs = [];
        (processedSemesters || []).forEach(sem => {
            (sem.subjects || []).forEach(sub => {
                if (!sub.passed) {
                    backlogs.push({
                        semester: sem.semester,
                        code: sub.code,
                        name: sub.name,
                        grade: sub.grade
                    });
                }
            });
        });
        return backlogs;
    }

    // Main Renderer function
    function renderJntuhMemoView(data, options) {
        options = options || {};
        const activeTab = options.activeTab || 'official'; // 'official' | 'cards' | 'backlogs' | 'credits'
        const roll = (data.student_id || data.roll || '').toUpperCase();
        const name = (data.name || data.student_name || roll || 'STUDENT NAME').toUpperCase();
        const fatherName = (data.fatherName || data.father_name || 'SHAIK MAHABOOB VALI').toUpperCase();
        const collegeName = getCollegeName(roll);
        const collegeCode = getCollegeCode(roll);
        const branchName = getBranchFullName(roll, data.department);

        let rawResults = data.results || [];
        if (typeof rawResults === 'string') {
            try { rawResults = JSON.parse(rawResults); } catch (e) { rawResults = []; }
        }

        const semList = processSemestersData(rawResults);

        // Compute CGPA & Credits
        let totalCreditsSecured = 0;
        let totalWeightedPoints = 0;
        semList.forEach(sem => {
            (sem.subjects || []).forEach(sub => {
                if (sub.passed && sub.credits > 0) {
                    totalCreditsSecured += sub.credits;
                    totalWeightedPoints += (sub.credits * sub.points);
                }
            });
        });

        const calculatedCgpa = totalCreditsSecured > 0 ? (totalWeightedPoints / totalCreditsSecured).toFixed(2) : '0.00';
        const displayCgpa = (data.cgpa !== undefined && data.cgpa !== null && data.cgpa > 0)
            ? Number(data.cgpa).toFixed(2)
            : calculatedCgpa;

        const backlogsList = getActiveBacklogs(semList);
        const backlogsCount = data.backlogsCount !== undefined ? data.backlogsCount : backlogsList.length;

        // Group Semesters into 4 Academic Years (1 to 4)
        const yearsMap = { 1: { sem1: null, sem2: null }, 2: { sem1: null, sem2: null }, 3: { sem1: null, sem2: null }, 4: { sem1: null, sem2: null } };
        semList.forEach(sem => {
            const sNum = sem.semester;
            if (sNum === 1) yearsMap[1].sem1 = sem;
            else if (sNum === 2) yearsMap[1].sem2 = sem;
            else if (sNum === 3) yearsMap[2].sem1 = sem;
            else if (sNum === 4) yearsMap[2].sem2 = sem;
            else if (sNum === 5) yearsMap[3].sem1 = sem;
            else if (sNum === 6) yearsMap[3].sem2 = sem;
            else if (sNum === 7) yearsMap[4].sem1 = sem;
            else if (sNum === 8) yearsMap[4].sem2 = sem;
        });

        const callbackFn = options.onTabChange || 'switchJntuhMemoTab';

        let html = `
        <div class="jntuh-memo-container">
            <!-- Navigation Control Bar -->
            <div class="jntuh-control-bar no-print">
                <div class="jntuh-tab-group">
                    <button class="jntuh-mode-btn ${activeTab === 'official' ? 'active' : ''}" onclick="${callbackFn}('${roll}', 'official')">
                        <i class="fas fa-file-invoice"></i> Official CMM Memo
                    </button>
                    <button class="jntuh-mode-btn ${activeTab === 'cards' ? 'active' : ''}" onclick="${callbackFn}('${roll}', 'cards')">
                        <i class="fas fa-th-large"></i> Semester Cards
                    </button>
                    <button class="jntuh-mode-btn ${activeTab === 'backlogs' ? 'active' : ''}" onclick="${callbackFn}('${roll}', 'backlogs')">
                        <i class="fas fa-exclamation-triangle"></i> Backlogs (${backlogsCount})
                    </button>
                    <button class="jntuh-mode-btn ${activeTab === 'credits' ? 'active' : ''}" onclick="${callbackFn}('${roll}', 'credits')">
                        <i class="fas fa-award"></i> Credits (${totalCreditsSecured.toFixed(1)})
                    </button>
                </div>
                <div class="jntuh-action-btns">
                    <button class="jntuh-print-btn" onclick="window.print()" title="Print or Save PDF">
                        <i class="fas fa-print"></i> Print / Save PDF
                    </button>
                </div>
            </div>`;

        if (activeTab === 'official') {
            // OFFICIAL JNTUH CMM MEMORANDUM FORMAT (Matching PDF Image)
            html += `
            <div class="cmm-paper-wrapper">
                <div class="cmm-paper">
                    <!-- University Header Banner -->
                    <div class="cmm-header-grid">
                        <div class="cmm-emblem emblem-left">
                            <div class="cmm-emblem-circle">
                                <span>JNTUH</span>
                                <small>SAMPLE</small>
                            </div>
                        </div>
                        <div class="cmm-header-text">
                            <h1 class="cmm-univ-title">JAWAHARLAL NEHRU TECHNOLOGICAL UNIVERSITY HYDERABAD</h1>
                            <div class="cmm-univ-location">HYDERABAD - 500 085, TELANGANA STATE, INDIA</div>
                            <div class="cmm-memo-badge">CONSOLIDATED MEMO OF MARKS / GRADES AND CREDITS</div>
                        </div>
                        <div class="cmm-emblem emblem-right">
                            <div class="cmm-emblem-circle">
                                <span>SAMPLE</span>
                                <small>SAMPLE</small>
                            </div>
                        </div>
                    </div>

                    <!-- Course & Student Info Box -->
                    <div class="cmm-info-card">
                        <div class="cmm-info-top-row">
                            <div class="cmm-doc-tag">CMM-SAMPLE</div>
                            <div class="cmm-degree-title">B.Tech. &nbsp; ${branchName}</div>
                        </div>
                        <div class="cmm-info-details-grid">
                            <div class="cmm-info-col">
                                <div class="cmm-info-line"><span class="cmm-lbl">Name</span><span class="cmm-sep">:</span><span class="cmm-val name-val">${name}</span></div>
                                <div class="cmm-info-line"><span class="cmm-lbl">Hall Ticket No.</span><span class="cmm-sep">:</span><span class="cmm-val roll-val">${roll}</span></div>
                                <div class="cmm-info-line"><span class="cmm-lbl">Father Name</span><span class="cmm-sep">:</span><span class="cmm-val">${fatherName}</span></div>
                                <div class="cmm-info-line"><span class="cmm-lbl">College Code</span><span class="cmm-sep">:</span><span class="cmm-val">${collegeCode}</span></div>
                            </div>
                            <div class="cmm-info-col">
                                <div class="cmm-info-line"><span class="cmm-lbl">Document</span><span class="cmm-sep">:</span><span class="cmm-val">CMM SAMPLE</span></div>
                                <div class="cmm-info-line"><span class="cmm-lbl">Credits Secured</span><span class="cmm-sep">:</span><span class="cmm-val highlight">${totalCreditsSecured.toFixed(1)}</span></div>
                                <div class="cmm-info-line"><span class="cmm-lbl">Aggregate CGPA</span><span class="cmm-sep">:</span><span class="cmm-val highlight">${displayCgpa}</span></div>
                            </div>
                        </div>
                    </div>

                    <!-- 4 Academic Years Semester Table Grid -->
                    <div class="cmm-tables-container">`;

            const yearLabels = { 1: 'I YEAR', 2: 'II YEAR', 3: 'III YEAR', 4: 'IV YEAR' };
            const romanSems = { 1: 'I SEMESTER', 2: 'II SEMESTER', 3: 'I SEMESTER', 4: 'II SEMESTER', 5: 'I SEMESTER', 6: 'II SEMESTER', 7: 'I SEMESTER', 8: 'II SEMESTER' };

            for (let y = 1; y <= 4; y++) {
                const s1Obj = yearsMap[y].sem1;
                const s2Obj = yearsMap[y].sem2;
                const s1Num = (y - 1) * 2 + 1;
                const s2Num = (y - 1) * 2 + 2;

                html += `
                <div class="cmm-year-block">
                    <div class="cmm-year-header-bar">${yearLabels[y]}</div>
                    <div class="cmm-year-columns">
                        <!-- Left Sem Column -->
                        <div class="cmm-sem-column">
                            <div class="cmm-sem-title-header">${romanSems[s1Num]}</div>
                            <table class="cmm-grid-table">
                                <thead>
                                    <tr>
                                        <th style="width:18%;">SUBJECT CODE</th>
                                        <th style="width:50%;">SUBJECT TITLE</th>
                                        <th style="width:10%;">GRADE POINT</th>
                                        <th style="width:10%;">GRADE</th>
                                        <th style="width:12%;">CREDITS</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                if (s1Obj && s1Obj.subjects && s1Obj.subjects.length > 0) {
                    s1Obj.subjects.forEach(sub => {
                        const isFail = !sub.passed;
                        html += `
                                    <tr class="${isFail ? 'row-failed' : ''}">
                                        <td class="col-code">${sub.code}</td>
                                        <td class="col-title">${sub.name}</td>
                                        <td class="col-center">${isFail ? '' : sub.points}</td>
                                        <td class="col-center grade-cell ${isFail ? 'fail-txt' : ''}">${sub.grade}</td>
                                        <td class="col-right">${sub.credits.toFixed(1)}</td>
                                    </tr>`;
                    });
                } else {
                    html += `<tr><td colspan="5" class="empty-sem-row">Results Not Released / Available</td></tr>`;
                }

                html += `
                                </tbody>
                            </table>
                        </div>

                        <!-- Right Sem Column -->
                        <div class="cmm-sem-column">
                            <div class="cmm-sem-title-header">${romanSems[s2Num]}</div>
                            <table class="cmm-grid-table">
                                <thead>
                                    <tr>
                                        <th style="width:18%;">SUBJECT CODE</th>
                                        <th style="width:50%;">SUBJECT TITLE</th>
                                        <th style="width:10%;">GRADE POINT</th>
                                        <th style="width:10%;">GRADE</th>
                                        <th style="width:12%;">CREDITS</th>
                                    </tr>
                                </thead>
                                <tbody>`;

                if (s2Obj && s2Obj.subjects && s2Obj.subjects.length > 0) {
                    s2Obj.subjects.forEach(sub => {
                        const isFail = !sub.passed;
                        html += `
                                    <tr class="${isFail ? 'row-failed' : ''}">
                                        <td class="col-code">${sub.code}</td>
                                        <td class="col-title">${sub.name}</td>
                                        <td class="col-center">${isFail ? '' : sub.points}</td>
                                        <td class="col-center grade-cell ${isFail ? 'fail-txt' : ''}">${sub.grade}</td>
                                        <td class="col-right">${sub.credits.toFixed(1)}</td>
                                    </tr>`;
                    });
                } else {
                    html += `<tr><td colspan="5" class="empty-sem-row">Results Not Released / Available</td></tr>`;
                }

                html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>`;
            }

            // Summary & Barcode Footer
            html += `
                    </div> <!-- /cmm-tables-container -->

                    <div class="cmm-footer-box">
                        <div class="cmm-summary-lines">
                            <div><strong>Number of Credits registered and secured are:</strong> <span>${totalCreditsSecured.toFixed(1)}</span></div>
                            <div><strong>Aggregate Marks / CGPA Secured:</strong> <span>${displayCgpa}</span></div>
                            <div><strong>Date of Issue:</strong> <span>—</span></div>
                        </div>

                        <div class="cmm-bottom-auth">
                            <div class="cmm-barcode-container">
                                <div class="cmm-barcode-lines">||| | |||| || ||| ||||| ||| |||| || |||</div>
                                <div class="cmm-barcode-url">jntuhconnect.dhethi.com</div>
                            </div>
                            <div class="cmm-controller-sign">
                                <div class="cmm-sign-title">CONTROLLER OF EXAMINATIONS</div>
                                <div class="cmm-sign-sub">(No signature shown — sample illustration)</div>
                            </div>
                        </div>

                        <div class="cmm-watermark-disclaimer">
                            SAMPLE DOCUMENT — NOT VALID FOR VERIFICATION OR OFFICIAL USE
                        </div>
                    </div>
                </div>
            </div>`;
        } else if (activeTab === 'cards') {
            // MODERN CARDS VIEW (Interactive Accordions)
            html += `
            <div class="jntuh-cards-wrapper">
                <div class="res-profile-card">
                    <div class="res-profile-top">
                        <div class="res-student-info">
                            <div class="res-student-name">${name}</div>
                            <div class="res-roll-number">${roll}</div>
                            <div class="res-branch-name">${branchName}</div>
                            <div class="res-college-name">${collegeName}</div>
                        </div>
                        <div class="res-cgpa-ring-wrapper">
                            <div class="res-cgpa-ring">
                                <div class="res-cgpa-val">${displayCgpa}</div>
                                <div class="res-cgpa-lbl">CGPA</div>
                            </div>
                        </div>
                    </div>
                    <div class="res-stats-grid">
                        <div class="res-stat-box"><div class="res-stat-num">${totalCreditsSecured.toFixed(1)}</div><div class="res-stat-lbl">Credits</div></div>
                        <div class="res-stat-box"><div class="res-stat-num">${backlogsCount}</div><div class="res-stat-lbl">Backlogs</div></div>
                        <div class="res-stat-box"><div class="res-stat-num">${semList.length}</div><div class="res-stat-lbl">Semesters</div></div>
                    </div>
                </div>`;

            if (semList.length > 0) {
                const semNotationMap = { 1: '1-1', 2: '1-2', 3: '2-1', 4: '2-2', 5: '3-1', 6: '3-2', 7: '4-1', 8: '4-2' };
                semList.forEach((sem, idx) => {
                    const semLabel = semNotationMap[sem.semester] || ('Sem ' + sem.semester);
                    const sgpaVal = (sem.sgpa || 0).toFixed(2);
                    const subList = sem.subjects || [];

                    html += `
                    <div class="res-sem-card" id="memo-sem-card-${idx}">
                        <div class="res-sem-header" onclick="document.getElementById('memo-sem-card-${idx}').classList.toggle('collapsed')">
                            <div>
                                <div class="res-sem-title">Semester ${semLabel} (${sem.type || 'Regular'})</div>
                                <div class="res-sem-meta">${sem.totalCredits.toFixed(1)} credits &middot; ${subList.length} subjects</div>
                            </div>
                            <div class="res-sem-right-badge">
                                <div class="res-sgpa-badge">SGPA <span>${sgpaVal}</span></div>
                                <div class="res-chevron">&#9650;</div>
                            </div>
                        </div>
                        <div class="res-subject-list">`;

                    subList.forEach(s => {
                        const internal = s.internal !== undefined && s.internal !== '' ? s.internal : '—';
                        const external = s.external !== undefined && s.external !== '' ? s.external : '—';
                        let totalVal = '—';
                        if (internal !== '—' && external !== '—' && !isNaN(parseFloat(internal)) && !isNaN(parseFloat(external))) {
                            totalVal = (parseFloat(internal) + parseFloat(external)).toFixed(0);
                        }

                        const gradeStr = (s.grade || '-').trim().toUpperCase();
                        let gradeClass = 'grade-a';
                        if (gradeStr === 'O' || gradeStr === '10') gradeClass = 'grade-o';
                        else if (gradeStr === 'A+' || gradeStr === '9') gradeClass = 'grade-a-plus';
                        else if (gradeStr === 'A' || gradeStr === '8') gradeClass = 'grade-a';
                        else if (gradeStr === 'B+' || gradeStr === '7') gradeClass = 'grade-b-plus';
                        else if (gradeStr === 'B' || gradeStr === '6') gradeClass = 'grade-b';
                        else if (gradeStr === 'C' || gradeStr === '5') gradeClass = 'grade-c';
                        else if (gradeStr === 'F' || gradeStr === 'AB' || gradeStr === 'ABSENT' || !s.passed) gradeClass = 'grade-f';

                        html += `
                            <div class="res-subject-item">
                                <div class="res-subj-left">
                                    <div class="res-subj-code">${s.code || '-'}</div>
                                    <div class="res-subj-name">${s.name || 'SUBJECT'}</div>
                                    <div class="res-subj-marks">Int: ${internal} &middot; Ext: ${external} &middot; Total: ${totalVal}</div>
                                </div>
                                <div class="res-subj-right">
                                    <div class="res-grade-pill ${gradeClass}">${s.grade || '-'}</div>
                                    <div class="res-credit-val">${s.credits !== undefined ? s.credits : '-'} cr</div>
                                </div>
                            </div>`;
                    });

                    html += `</div></div>`;
                });
            } else {
                html += `<div class="res-sem-card" style="padding:24px; text-align:center; color:#94a3b8;">No semester results available.</div>`;
            }
            html += `</div>`;
        } else if (activeTab === 'backlogs') {
            // BACKLOGS VIEW
            html += `<div class="jntuh-backlogs-wrapper">`;
            if (backlogsList.length === 0) {
                html += `
                <div class="res-sem-card" style="padding:36px; text-align:center;">
                    <div style="font-size:44px; margin-bottom:12px;">🎉</div>
                    <h3 style="color:#34d399; margin:0 0 6px; font-weight:800;">Zero Active Backlogs</h3>
                    <p style="color:#94a3b8; font-size:14px; margin:0;">Congratulations! All registered subjects have been passed successfully.</p>
                </div>`;
            } else {
                html += `
                <div style="margin-bottom:14px; font-weight:700; color:#f87171; font-size:15px;">
                    Active Backlog Subjects (${backlogsList.length})
                </div>`;
                backlogsList.forEach(b => {
                    html += `
                    <div class="res-sem-card" style="padding:18px 22px; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div class="res-subj-code">SEMESTER ${b.semester} &middot; ${b.code}</div>
                                <div class="res-subj-name" style="font-size:15px; margin-top:2px;">${b.name}</div>
                            </div>
                            <div class="res-grade-pill grade-f" style="width:38px; height:38px; font-size:16px;">${b.grade || 'F'}</div>
                        </div>
                    </div>`;
                });
            }
            html += `</div>`;
        } else if (activeTab === 'credits') {
            // CREDITS TRACKER VIEW
            const degreeTarget = 160;
            const pct = Math.min(100, Math.round((totalCreditsSecured / degreeTarget) * 100));
            html += `
            <div class="jntuh-credits-wrapper">
                <div class="res-sem-card" style="padding:24px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                        <div>
                            <h3 style="margin:0 0 4px; color:#ffffff; font-size:18px;">Degree Credit Requirement</h3>
                            <p style="margin:0; color:#94a3b8; font-size:13.5px;">B.Tech 4-Year Graduation Target: 160 Credits</p>
                        </div>
                        <div style="font-size:22px; font-weight:800; color:#38bdf8;">
                            ${totalCreditsSecured.toFixed(1)} / ${degreeTarget} <span style="font-size:14px;">(${pct}%)</span>
                        </div>
                    </div>
                    <div style="background:#0d1019; height:12px; border-radius:10px; overflow:hidden; border:1px solid #28334a;">
                        <div style="width:${pct}%; background:linear-gradient(90deg, #38bdf8, #34d399); height:100%;"></div>
                    </div>
                    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-top:20px;">
                        <div style="background:#181d2d; padding:14px; border-radius:12px; text-align:center;">
                            <div style="color:#94a3b8; font-size:12px;">Promotion to 2nd Year</div>
                            <div style="color:${totalCreditsSecured >= 20 ? '#34d399' : '#f87171'}; font-weight:800; font-size:15px; margin-top:4px;">
                                ${totalCreditsSecured >= 20 ? 'Eligible (≥20 cr)' : 'Ineligible (<20 cr)'}
                            </div>
                        </div>
                        <div style="background:#181d2d; padding:14px; border-radius:12px; text-align:center;">
                            <div style="color:#94a3b8; font-size:12px;">Promotion to 3rd Year</div>
                            <div style="color:${totalCreditsSecured >= 48 ? '#34d399' : '#f87171'}; font-weight:800; font-size:15px; margin-top:4px;">
                                ${totalCreditsSecured >= 48 ? 'Eligible (≥48 cr)' : 'Ineligible (<48 cr)'}
                            </div>
                        </div>
                        <div style="background:#181d2d; padding:14px; border-radius:12px; text-align:center;">
                            <div style="color:#94a3b8; font-size:12px;">Promotion to 4th Year</div>
                            <div style="color:${totalCreditsSecured >= 72 ? '#34d399' : '#f87171'}; font-weight:800; font-size:15px; margin-top:4px;">
                                ${totalCreditsSecured >= 72 ? 'Eligible (≥72 cr)' : 'Ineligible (<72 cr)'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>`;
        }

        html += `</div>`;
        return html;
    }

    // Expose helpers globally
    global.renderJntuhMemoView = renderJntuhMemoView;
    global.getBranchFullName = getBranchFullName;
    global.getCollegeName = getCollegeName;
    global.getCollegeCode = getCollegeCode;
    global.processSemestersData = processSemestersData;
    global.getActiveBacklogs = getActiveBacklogs;

})(typeof window !== 'undefined' ? window : this);
