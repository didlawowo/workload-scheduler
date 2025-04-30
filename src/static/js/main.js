const modal = document.getElementById('cronModal');
const closeBtn = document.querySelector('.close');
const saveBtn = document.getElementById('saveBtn');
const cronStart = document.getElementById('cronExpressionStart');
const cronStop = document.getElementById('cronExpressionStop');
const cronError = document.getElementById('cronError');
const deleteBtn = document.getElementById('deleteBtn');


/* main */

function toggleWorkloadDetails(button) {
    const podDetails = button.closest('.pod-details');
    podDetails.classList.toggle('collapsed');
    button.textContent = podDetails.classList.contains('collapsed') ? 'Show Details' : 'Hide Details';
}

function manageWorkloadStatus(type, name, uid, action) {
    let url = ``;
    if (action === 'down') {
        url = `/manage/down/${type}/${uid}`;
    } else if (action === 'up') {
        url = `/manage/up/${type}/${uid}`;
    } else if (action === 'down-all') {
        url = `/manage-all/down`;
    } else if (action === 'up-all') {
        url = `/manage-all/up`;
    }
    
    console.log(`URL: ${url}`);
    
    fetch(url, { method: 'GET' })
        .then(response => {
            console.log(`Réponse reçue, status: ${response.status}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const contentType = response.headers.get('content-type');
            console.log(`Type de contenu: ${contentType}`);
            
            if (contentType && contentType.includes('application/json')) {
                return response.json().then(data => {
                    return { isJson: true, data: data };
                });
            } else {
                return response.text().then(text => {
                    console.log("Réponse texte:", text);
                    return { isJson: false, data: { status: 'success', message: text || 'Opération effectuée' } };
                });
            }
        })
        .then(result => {
            console.log("Traitement de la réponse:", result);
            
            console.log("Attente avant rechargement...");
            setTimeout(() => {
                console.log("Rechargement de la page...");
                window.location.reload();
            }, 1000);
        })
        .catch(error => {
            console.error('Erreur:', error);
            alert(`Une erreur est survenue: ${error.message}`);
        });
}

/* modal management */

// Fonction pour fermer le modal et réinitialiser son état
function closeModal() {
    modal.style.display = 'none';
    saveBtn.dataset.mode = 'create';
    document.querySelector('.modal-content').dataset.mode = 'create';
    document.querySelector('.modal-content h3').textContent = 'Éditeur d\'expression Cron';
    deleteBtn.style.display = 'none';
    currentScheduleId = null;
    
    refreshCronDisplay();
}

closeBtn.addEventListener('click', closeModal);

/* crontab management */
let defaultCronValue = "";
let currentCronStartValue = defaultCronValue;
let currentCronStopValue = defaultCronValue;
let currentAction, currentName, currentDirection, currentUid;
let currentScheduleId = null;
let currentStatus = "not scheduled";
let currentNamespace = "";

function isValidCron(expression) {
    if (!expression) return true; // Empty string is considered valid

    const cleanedExpression = expression.replace(/\s+/g, ' ').trim();

    const parts = cleanedExpression.split(' ');

    if (parts.length !== 5) return false;

    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

    // Minute: 0-59 ou */n ou * ou liste (1,2,3) ou plage (1-5)
    const minutePattern = /^(\*|([0-9]|[1-5][0-9])(,([0-9]|[1-5][0-9]))*)$|^\*\/([1-9]|[1-5][0-9])$|^([0-9]|[1-5][0-9])-([0-9]|[1-5][0-9])$/;
    if (!minutePattern.test(minute)) return false;

    // Heure: 0-23 ou */n ou * ou liste ou plage
    const hourPattern = /^(\*|([0-9]|1[0-9]|2[0-3])(,([0-9]|1[0-9]|2[0-3]))*)$|^\*\/([1-9]|1[0-9]|2[0-3])$|^([0-9]|1[0-9]|2[0-3])-([0-9]|1[0-9]|2[0-3])$/;
    if (!hourPattern.test(hour)) return false;

    // Jour du mois: 1-31 ou */n ou * ou liste ou plage
    const dayOfMonthPattern = /^(\*|([1-9]|[12][0-9]|3[01])(,([1-9]|[12][0-9]|3[01]))*)$|^\*\/([1-9]|[12][0-9]|3[01])$|^([1-9]|[12][0-9]|3[01])-([1-9]|[12][0-9]|3[01])$/;
    if (!dayOfMonthPattern.test(dayOfMonth)) return false;

    // Mois: 1-12 ou */n ou * ou liste ou plage
    const monthPattern = /^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*)$|^\*\/([1-9]|1[0-2])$|^([1-9]|1[0-2])-([1-9]|1[0-2])$/;
    if (!monthPattern.test(month)) return false;

    // Jour de la semaine: 0-6 ou */n ou * ou liste ou plage
    const dayOfWeekPattern = /^(\*|([0-6])(,[0-6])*)$|^\*\/[1-6]$|^[0-6]-[0-6]$/;
    if (!dayOfWeekPattern.test(dayOfWeek)) return false;

    return true;
}

function cleanCronExpression(expression) {
    if (!expression) return "";

    let cleaned = expression.replace(/\s+/g, ' ').trim();

    if (cleaned === "") return "";

    const parts = cleaned.split(' ');

    while (parts.length < 5) {
      parts.push('*');
    }

    if (parts.length > 5) {
      cleaned = parts.slice(0, 5).join(' ');
    }

    return cleaned;
}

// Fonction pour éditer une programmation
function edit_prog(uid, resourceName = "", resourceType = "deploy", direction = "up") {
    currentUid = uid;
    
    currentName = resourceName;
    currentAction = resourceType;
    currentDirection = direction;
    currentNamespace = ""; 
    
    cronStart.value = defaultCronValue;
    cronStop.value = defaultCronValue;
    cronError.style.display = 'none';
    
    console.log(`Récupération des données pour l'UID: ${uid}`);
    
    deleteBtn.style.display = 'none';
    
    fetch(`/schedule/${uid}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (response.status === 404) {
            console.log(`Aucun schedule existant pour l'UID: ${uid}`);
            return null;
        }
        if (!response.ok) {
            throw new Error(`Erreur réseau: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Schedule data:", data);
        
        if (data && data.id) {
            console.log(`Schedule existant trouvé pour l'UID: ${uid}, ID: ${data.id}`);
            cronStart.value = data.cron_start ? cleanCronExpression(data.cron_start) : defaultCronValue;
            cronStop.value = data.cron_stop ? cleanCronExpression(data.cron_stop) : defaultCronValue;
            currentScheduleId = data.id;
            
            const hasCronExpressions =
                data.cron_start !== "" &&
                data.cron_stop !== "";
            
            if (data.name) {
                let currentWorkloadNameField = document.getElementById('currentWorkloadName');
                if (!currentWorkloadNameField) {
                    currentWorkloadNameField = document.createElement('input');
                    currentWorkloadNameField.type = 'hidden';
                    currentWorkloadNameField.id = 'currentWorkloadName';
                    document.querySelector('.modal-content').appendChild(currentWorkloadNameField);
                }
                currentWorkloadNameField.value = data.name;
                console.log(`Nom actuel du workload préservé: ${data.name}`);
            }
            
            saveBtn.dataset.mode = 'update';
            document.querySelector('.modal-content').dataset.mode = 'update';
            document.querySelector('.modal-content h3').textContent = 'Modifier la programmation';
            
            deleteBtn.style.display = hasCronExpressions ? 'inline-block' : 'none';
            
            currentStatus = data.status;
            
            if (resourceName) {
                currentName = resourceName;
            }
            
        } else {
            console.log(`Création d'un nouveau schedule pour l'UID: ${uid}`);
            currentScheduleId = null;
            saveBtn.dataset.mode = 'create';
            document.querySelector('.modal-content').dataset.mode = 'create';
            document.querySelector('.modal-content h3').textContent = 'Nouvelle programmation';
            currentStatus = "not scheduled";
            
            deleteBtn.style.display = 'none';
        }
        
        console.log("Workload info:", {
            action: currentAction,
            name: currentName,
            direction: currentDirection,
            uid: currentUid,
            scheduleId: currentScheduleId,
            mode: saveBtn.dataset.mode,
            status: currentStatus
        });
        
        // Important: Update the cron info display immediately after loading the values
        updateCronInfo();
    })
    .catch(error => {
        console.error('Erreur lors de la vérification des programmations:', error);
        currentScheduleId = null;
        saveBtn.dataset.mode = 'create';
        document.querySelector('.modal-content').dataset.mode = 'create';
        document.querySelector('.modal-content h3').textContent = 'Nouvelle programmation';
        currentStatus = "not scheduled";
        
        deleteBtn.style.display = 'none';
        
        // Also update cron info even in case of error
        updateCronInfo();
    })
    .finally(() => {
        modal.style.display = 'block';
    });
}

// Charger les programmations au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    const cronStartInput = document.getElementById('cronExpressionStart');
    const cronStopInput = document.getElementById('cronExpressionStop');

    if (cronStartInput && cronStopInput) {
        cronStartInput.addEventListener('input', updateCronInfo);
        cronStopInput.addEventListener('input', updateCronInfo);

        // Make sure cronInfoDiv exists
        let cronInfoDiv = document.getElementById('cronInfo');
        if (!cronInfoDiv) {
            cronInfoDiv = document.createElement('div');
            cronInfoDiv.id = 'cronInfo';
            const formGroup = document.querySelector('.form-group');
            if (formGroup) {
                formGroup.appendChild(cronInfoDiv);
            }
        }
    }
    
    // Ajout : Chargement et affichage des crons pour tous les workloads
    loadAllCronSchedules();
    
    // Écouter le bouton de suppression
    const deleteBtn = document.getElementById('deleteBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', () => {
            if (currentScheduleId) {
                deleteSchedule(currentScheduleId);
            } else {
                alert("Aucune programmation à supprimer.");
            }
        });
    }
});

// Mettre à jour le gestionnaire d'événements pour le bouton "saveBtn"
saveBtn.addEventListener('click', () => {
    const cron_start_value = cleanCronExpression(cronStart.value.trim());
    const cron_stop_value = cleanCronExpression(cronStop.value.trim());

    cronStart.value = cron_start_value;
    cronStop.value = cron_stop_value;

    if ((cron_start_value !== "" && !isValidCron(cron_start_value)) || 
        (cron_stop_value !== "" && !isValidCron(cron_stop_value))){
        cronError.style.display = 'block';
        cronError.textContent = `Expression CRON invalide. Format attendu: minute heure jour_du_mois mois jour_de_la_semaine`;
        return;
    }

    cronError.style.display = 'none';
    currentCronStartValue = cron_start_value;
    currentCronStopValue = cron_stop_value;
    
    const isUpdate = saveBtn.dataset.mode === 'update' && currentScheduleId;
    
    if (!currentName) {
        cronError.style.display = 'block';
        cronError.textContent = `Le nom du déploiement est manquant. Veuillez spécifier un nom.`;
        return;
    }
    
    // Générer le nom du workload uniquement pour les nouveaux workloads, pas pour les mises à jour
    const workloadName = isUpdate ? document.getElementById('currentWorkloadName')?.value || `${currentAction}-${currentName}-${currentDirection}` : `${currentAction}-${currentName}-${currentDirection}`;
    
    console.log("Nom du workload à utiliser:", workloadName);
    console.log("Mode:", isUpdate ? "UPDATE" : "CREATE", "ScheduleID:", currentScheduleId);

    const nowStr = new Date().toISOString();

    const hasCronExpression = currentCronStartValue !== "" || currentCronStopValue !== "";
    const workloadStatus = hasCronExpression ? "scheduled" : "not scheduled";

    if (isUpdate) {
        console.log(`Mise à jour du schedule ID: ${currentScheduleId}`);
        fetch(`/schedules/${currentScheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: currentScheduleId,
                cron_start: currentCronStartValue,
                cron_stop: currentCronStopValue,
                uid: currentUid,
                active: true,
                last_update: nowStr,
                status: workloadStatus
            })
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errorData => {
                    throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Programmation mise à jour:', data);
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la mise à jour de la programmation:', error);
            alert(`Erreur lors de la mise à jour de la programmation: ${error.message}`);
        });
    } else {
        console.log(`Création d'un nouveau schedule pour UID: ${currentUid}`);
        fetch('/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: workloadName,
                uid: currentUid,
                cron_start: currentCronStartValue,
                cron_stop: currentCronStopValue,
                status: workloadStatus,
                active: true,
                resource_type: currentAction,
                resource_name: currentName,
                resource_namespace: currentNamespace,
                direction: currentDirection,
                last_update: nowStr
            })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Programmation créée:', data);
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la création de la programmation:', error);
            alert(`Erreur lors de la création de la programmation: ${error.message}`);

            console.error('Data sent:', {
                name: workloadName,
                uid: currentUid,
                cron_start: currentCronStartValue,
                cron_stop: currentCronStopValue,
                resource_name: currentName,
                status: workloadStatus
            });
        });
    }
});

// Fonction pour charger tous les schedules et les afficher
function loadAllCronSchedules() {
    fetch('/schedules', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erreur réseau: ' + response.status);
        }
        return response.json();
    })
    .then(schedules => {
        console.log('Programmations récupérées:', schedules);
        
        // Créer un mapping des programmations par UID
        const schedulesByUid = {};
        schedules.forEach(schedule => {
            if (schedule.uid) {
                schedulesByUid[schedule.uid] = schedule;
            }
        });
        
        // Rechercher les boutons d'édition pour trouver les workloads et mettre à jour leurs crons
        const editButtons = document.querySelectorAll('button[onclick^="edit_prog"]');
        editButtons.forEach(button => {
            // Extraire l'UID du bouton edit_prog
            const onclickAttr = button.getAttribute('onclick');
            const match = onclickAttr.match(/edit_prog\('([^']+)'/);
            
            if (match && match[1]) {
                const uid = match[1];
                const schedule = schedulesByUid[uid];
                
                if (schedule) {
                    updateWorkloadCronDisplay(schedule);
                }
            }
        });
    })
    .catch(error => {
        console.error('Erreur lors de la récupération des programmations:', error);
    });
}

// Fonction pour mettre à jour l'affichage des crons d'un workload
function updateWorkloadCronDisplay(schedule) {
    const editButtons = document.querySelectorAll(`button[onclick*="'${schedule.uid}'"]`);
    
    if (editButtons.length === 0) {
        console.log(`Aucun workload trouvé avec l'UID: ${schedule.uid}`);
        return;
    }
    
    editButtons.forEach(button => {
        const parentCell = button.closest('td');
        
        const cronCell = parentCell.nextElementSibling;
        
        if (cronCell && cronCell.querySelector('.cron-info')) {
            const cronStartDisplay = schedule.cron_start ? schedule.cron_start : 'Not set';
            const cronStopDisplay = schedule.cron_stop ? schedule.cron_stop : 'Not set';
            
            cronCell.querySelector('.cron-info').innerHTML = `
                <div class="${schedule.cron_start ? 'cron-active' : ''}"><strong>Start:</strong> ${cronStartDisplay}</div>
                <div class="${schedule.cron_stop ? 'cron-active' : ''}"><strong>Stop:</strong> ${cronStopDisplay}</div>
            `;
        }
    });
}

// Fonction pour actualiser l'affichage des crons
function refreshCronDisplay() {
    loadAllCronSchedules();
}

// Fonction pour supprimer une programmation
function deleteSchedule(scheduleId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer cette programmation ?')) {
        fetch(`/schedules/${scheduleId}`, {
            method: 'DELETE'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Erreur réseau: ' + response.status);
            }
            return response.json();
        })
        .then(data => {
            console.log('Programmation supprimée:', data);
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la suppression de la programmation:', error);
        });
    }
}

deleteBtn.addEventListener('click', () => {
    if (!currentUid) {
        closeModal();
        return;
    }
    
    if (confirm('Êtes-vous sûr de vouloir supprimer cette programmation Cron ?')) {
        fetch(`/schedule/${currentUid}/remove-crons`, {
            method: 'PUT'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Expressions Cron supprimées:', data);
            refreshCronDisplay();  // Changed from getListSchedule() which doesn't exist
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la suppression des expressions Cron:', error);
            alert(`Erreur lors de la suppression des expressions Cron: ${error.message}`);
        });
    }
});

function decodeCronExpression(expression) {
    if (expression === "") {
        return "Non programmé";
    }
    
    if (!isValidCron(expression)) {
        return "Expression cron invalide";
    }
    
    const parts = expression.split(' ');
    if (parts.length !== 5) {
        return "Format d'expression cron invalide";
    }
    
    return generateSummary(parts);
}

function formatHour(hour) {
    const hourNum = parseInt(hour);
    if (hourNum === 0) return "minuit";
    if (hourNum === 12) return "midi";
    if (hourNum < 12) return `${hourNum}h du matin`;
    return `${hourNum-12}h de l'après-midi`;
}

function generateSummary(parts) {
    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
    
    if (minute === '0' && hour === '0' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        return "S'exécute à minuit tous les jours";
    }
    
    if (minute === '0' && dayOfMonth === '*' && month === '*') {
        if (hour === '9' && dayOfWeek === '1-5') {
            return "S'exécute à 9h du matin les jours de semaine";
        }
        if (hour === '17' && dayOfWeek === '1-5') {
            return "S'exécute à 17h les jours de semaine";
        }
    }
    
    if (minute.includes('/') && hour === '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        const interval = minute.split('/')[1];
        return `S'exécute toutes les ${interval} minute(s)`;
    }
    
    if (minute === '0' && hour.includes('/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
        const interval = hour.split('/')[1];
        return `S'exécute toutes les ${interval} heure(s) à l'heure pile`;
    }
    
    if (minute === '0' && hour === '0' && dayOfMonth === '*' && month === '*' && dayOfWeek === '0') {
        return "S'exécute à minuit les dimanches";
    }
    
    if (minute === '0' && hour === '0' && dayOfMonth === '1' && month === '*' && dayOfWeek === '*') {
        return "S'exécute à minuit le premier jour de chaque mois";
    }
    
    let time = "";
    if (minute === '*') {
        time = "chaque minute";
    } else if (minute.includes('/')) {
        time = `toutes les ${minute.split('/')[1]} minute(s)`;
    } else {
        time = `à la minute ${minute}`;
    }
    
    if (hour !== '*') {
        if (hour.includes('/')) {
            time += ` de chaque ${hour.split('/')[1]} heure(s)`;
        } else {
            const hourNum = parseInt(hour);
            time += ` de l'heure ${hourNum} (${formatHour(hour)})`;
        }
    }
    
    let days = "";
    if (dayOfMonth !== '*' && dayOfWeek !== '*') {
        days = `le ${dayOfMonth} du mois et le ${translateDayOfWeek(dayOfWeek)}`;
    } else if (dayOfMonth !== '*') {
        days = `le ${dayOfMonth} du mois`;
    } else if (dayOfWeek !== '*') {
        days = `le ${translateDayOfWeek(dayOfWeek)}`;
    }
    
    let months = "";
    if (month !== '*') {
        months = ` pendant ${translateMonth(month)}`;
    }
    
    return `S'exécute ${time}${days ? ' ' + days : ''}${months}`;
}

function translateDayOfWeek(dayOfWeek) {
    const dayNames = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
    
    if (dayOfWeek.includes('-')) {
        const [start, end] = dayOfWeek.split('-');
        const startDay = dayNames[parseInt(start)] || start;
        const endDay = dayNames[parseInt(end)] || end;
        return `du ${startDay} au ${endDay}`;
    }
    
    if (dayOfWeek.includes(',')) {
        const days = dayOfWeek.split(',');
        return days.map(d => dayNames[parseInt(d)] || d).join(', ');
    }
    
    const dayIndex = parseInt(dayOfWeek);
    if (dayIndex >= 0 && dayIndex <= 6) {
        return dayNames[dayIndex];
    }
    
    return `jour ${dayOfWeek} de la semaine`;
}

function translateMonth(month) {
    const monthNames = ["janvier", "février", "mars", "avril", "mai", "juin", 
                       "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
    
    if (month.includes('-')) {
        const [start, end] = month.split('-');
        const startMonth = monthNames[parseInt(start) - 1] || start;
        const endMonth = monthNames[parseInt(end) - 1] || end;
        return `de ${startMonth} à ${endMonth}`;
    }
    
    if (month.includes(',')) {
        const months = month.split(',');
        return months.map(m => monthNames[parseInt(m) - 1] || m).join(', ');
    }
    
    const monthIndex = parseInt(month) - 1;
    if (monthIndex >= 0 && monthIndex < 12) {
        return monthNames[monthIndex];
    }
    
    return `mois ${month}`;
}

function updateCronInfo() {
    const cronStartValue = document.getElementById('cronExpressionStart').value;
    const cronStopValue = document.getElementById('cronExpressionStop').value;
    
    let cronInfoDiv = document.getElementById('cronInfo');
    if (!cronInfoDiv) {
        cronInfoDiv = document.createElement('div');
        cronInfoDiv.id = 'cronInfo';
        const formGroup = document.querySelector('.form-group');
        if (formGroup) {
            formGroup.appendChild(cronInfoDiv);
        } else {
            console.error("No form-group element found to append cronInfo");
            return;
        }
    }
    
    let htmlContent = '<div class="cron-helper">';
    
    if (cronStartValue && isValidCron(cronStartValue)) {
        htmlContent += `<p><strong>Démarrage:</strong> ${decodeCronExpression(cronStartValue)}</p>`;
    } else if (cronStartValue === "") {
        htmlContent += `<p><strong>Démarrage:</strong> Non programmé</p>`;
    }
    
    if (cronStopValue && isValidCron(cronStopValue)) {
        htmlContent += `<p><strong>Arrêt:</strong> ${decodeCronExpression(cronStopValue)}</p>`;
    } else if (cronStopValue === "") {
        htmlContent += `<p><strong>Arrêt:</strong> Non programmé</p>`;
    }
    
    htmlContent += `
        <p><strong>Format:</strong> minute heure jour_du_mois mois jour_de_la_semaine</p>`;
    
    htmlContent += '</div>';
    cronInfoDiv.innerHTML = htmlContent;
}