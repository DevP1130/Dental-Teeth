const fileInput = document.getElementById('fileInput')
const uploadBtn = document.getElementById('uploadBtn')
const messages = document.getElementById('messages')
const resultDiv = document.getElementById('result')
const resultImg = document.getElementById('resultImg')
const aiSummaryDiv = document.getElementById('aiSummary')
const sendDoctorBtn = document.getElementById('sendDoctorBtn')
const sendStatus = document.getElementById('sendStatus')
const cameraBtn = document.getElementById('cameraBtn')
const fileLabel = document.getElementById('fileLabel')
const fileNameSpan = document.getElementById('fileName')
const cameraContainer = document.getElementById('cameraContainer')
const cameraVideo = document.getElementById('cameraVideo')
const captureBtn = document.getElementById('captureBtn')
const cancelCameraBtn = document.getElementById('cancelCameraBtn')
const retakeBtn = document.getElementById('retakeBtn')
const capturePreview = document.getElementById('capturePreview')
let cameraStream = null
let lastCapturedBlob = null

// simple HTML escaper to render AI text safely
function escapeHtml(str){
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// Loading bar functionality
function showLoadingBar() {
  const loadingContainer = document.getElementById('loadingContainer')
  const progressFill = document.getElementById('progressFill')
  const progressText = document.getElementById('progressText')
  const loadingStatus = document.getElementById('loadingStatus')
  const steps = ['step1', 'step2', 'step3', 'step4']
  
  // Hide result and show loading
  if (resultDiv) resultDiv.style.display = 'none'
  loadingContainer.style.display = 'block'
  
  // Reset progress
  progressFill.style.width = '0%'
  progressText.textContent = '0%'
  
  // Reset all steps
  steps.forEach(stepId => {
    const step = document.getElementById(stepId)
    if (step) {
      step.classList.remove('active', 'completed')
    }
  })
  
  // Simulate progress steps
  let currentStep = 0
  let progress = 0
  
  const progressInterval = setInterval(() => {
    // Update progress bar
    progress += Math.random() * 8 + 2 // Random increment between 2-10%
    if (progress > 95) progress = 95 // Don't complete until actual response
    
    progressFill.style.width = progress + '%'
    progressText.textContent = Math.round(progress) + '%'
    
    // Update steps
    const targetStep = Math.floor(progress / 25) // Each step at 25% intervals
    if (targetStep > currentStep && targetStep < steps.length) {
      // Mark previous step as completed
      if (currentStep > 0) {
        const prevStep = document.getElementById(steps[currentStep - 1])
        if (prevStep) {
          prevStep.classList.remove('active')
          prevStep.classList.add('completed')
        }
      }
      
      // Mark current step as active
      const activeStep = document.getElementById(steps[targetStep])
      if (activeStep) {
        activeStep.classList.add('active')
      }
      
      currentStep = targetStep + 1
      
      // Update status text
      const statusTexts = [
        'Uploading your dental image...',
        'Running AI analysis on dental structures...',
        'Generating detailed results...',
        'Finalizing comprehensive report...'
      ]
      if (statusTexts[targetStep]) {
        loadingStatus.textContent = statusTexts[targetStep]
      }
    }
  }, 200)
  
  return { progressInterval, progressFill, progressText, steps }
}

function hideLoadingBar(progressData) {
  const loadingContainer = document.getElementById('loadingContainer')
  
  if (progressData) {
    // Complete the progress bar
    clearInterval(progressData.progressInterval)
    progressData.progressFill.style.width = '100%'
    progressData.progressText.textContent = '100%'
    
    // Mark all steps as completed
    progressData.steps.forEach(stepId => {
      const step = document.getElementById(stepId)
      if (step) {
        step.classList.remove('active')
        step.classList.add('completed')
      }
    })
    
    // Show completion briefly before hiding
    setTimeout(() => {
      loadingContainer.style.display = 'none'
    }, 800)
  } else {
    loadingContainer.style.display = 'none'
  }
}

if (uploadBtn) uploadBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  // If there's a captured blob from the camera preview, upload that. Otherwise use the selected file.
  const fd = new FormData()
  if (lastCapturedBlob){
    fd.append('image', lastCapturedBlob, 'capture.jpg')
  } else {
    if (!fileInput.files || fileInput.files.length === 0){
      messages.textContent = 'Select a file first.'
      return
    }
    const f = fileInput.files[0]
    fd.append('image', f)
  }
  // include pre-upload concern if provided
  const preConcern = (document.getElementById('concernText')||{value:''}).value.trim()
  if (preConcern) fd.append('concern', preConcern)
  
  // Disable button and show loading
  uploadBtn.disabled = true
  uploadBtn.textContent = 'Processing...'
  const progressData = showLoadingBar()
  
  try{
    const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
    const data = await res.json()
    
    if (!data.success){
      hideLoadingBar()
      messages.textContent = data.error || 'Upload failed'
      uploadBtn.disabled = false
      uploadBtn.textContent = 'Upload and Scan'
      return
    }
    
    // Complete loading bar
    hideLoadingBar(progressData)
    
    // show the result image
    if (resultImg) resultImg.src = data.result_url + '?_=' + Date.now()
    // store uploaded filename for reference
    if (resultDiv) {
      resultDiv.dataset.uploadedFilename = data.uploaded_filename || ''
      resultDiv.style.display = 'block'
    }
    
    // display AI summary if present
    if (aiSummaryDiv){
      const disclaimerHtml = '<div class="ai-disclaimer">This AI-generated summary is provided for informational purposes only and is not a substitute for professional dental or medical advice, diagnosis, or treatment. Please consult a qualified healthcare provider for any concerns.</div>'
      if (data.ai_summary){
        aiSummaryDiv.innerHTML = '<h3>AI summary</h3><pre>' + escapeHtml(data.ai_summary) + '</pre>' + disclaimerHtml
        aiSummaryDiv.style.display = 'block'
      } else if (data.ai_summary_error){
        aiSummaryDiv.innerHTML = '<h3>AI summary</h3><pre>' + escapeHtml(data.ai_summary_error) + '</pre>' + disclaimerHtml
        aiSummaryDiv.style.display = 'block'
      } else {
        aiSummaryDiv.style.display = 'none'
        aiSummaryDiv.innerHTML = ''
      }
    }
    
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }catch(err){
    hideLoadingBar()
    messages.textContent = err.message || 'Network error'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }
})

// Send to doctor flow
if (sendDoctorBtn){
  sendDoctorBtn.addEventListener('click', async ()=>{
    sendStatus.textContent = ''
    sendDoctorBtn.disabled = true
    sendDoctorBtn.textContent = 'Sending...'

    // uploaded filename stored on result div dataset
    const uploaded = (resultDiv && resultDiv.dataset && resultDiv.dataset.uploadedFilename) || ''
    // prefer pre-upload concern textarea if present
    const concern = (document.getElementById('concernText')||{value:''}).value.trim()

    try{
      const res = await fetch('/send-to-doctor', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ uploaded_filename: uploaded, concern })
      })

      // Read as text first — server may return HTML (error page) instead of JSON
      const raw = await res.text()
      let data
      try {
        data = raw ? JSON.parse(raw) : {}
      } catch (parseErr) {
        // Not valid JSON (likely HTML error page). Surface the text (trim to reasonable length).
        const snippet = raw && raw.length > 1000 ? raw.slice(0,1000) + '…' : raw
        data = { success: res.ok, error: snippet || (res.statusText || 'Unknown error') }
      }

      if (data && data.success){
        sendStatus.textContent = 'Sent ✓'
      } else {
        sendStatus.textContent = 'Error: ' + (data.error || data.message || 'failed')
      }
    }catch(err){
      sendStatus.textContent = 'Network error: ' + err.message
    }

    sendDoctorBtn.disabled = false
    sendDoctorBtn.textContent = 'Send to doctor'
    setTimeout(()=>{ sendStatus.textContent = '' }, 8000)
  })
}

// show selected filename when user picks a file
if (fileInput){
  fileInput.addEventListener('change', ()=>{
    const f = (fileInput.files && fileInput.files[0])
    if (f){
      fileNameSpan.textContent = f.name
      fileLabel.textContent = 'Change image'
    } else {
      fileNameSpan.textContent = ''
      fileLabel.textContent = 'Choose image'
    }
  })
}

// Camera flow
if (cameraBtn) cameraBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  try{
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    cameraVideo.srcObject = cameraStream
    cameraContainer.style.display = 'block'
  }catch(err){
    messages.textContent = 'Could not access camera: ' + err.message
  }
})

if (cancelCameraBtn) cancelCameraBtn.addEventListener('click', ()=>{
  stopCamera()
})

if (captureBtn) captureBtn.addEventListener('click', async ()=>{
  if (!cameraStream) return
  // capture a frame from the video
  try{
    const track = cameraStream.getVideoTracks()[0]
    if (window.ImageCapture && typeof ImageCapture === 'function'){
      const imageCapture = new ImageCapture(track)
      if (typeof imageCapture.grabFrame === 'function'){
  const bitmap = await imageCapture.grabFrame()
  await captureBitmapAndCrop(bitmap)
      } else {
        // fallback to canvas drawImage from video
        await captureFromVideoToCanvas()
      }
    } else {
      // fallback to canvas drawImage from video
      await captureFromVideoToCanvas()
    }
  }catch(err){
    messages.textContent = 'Capture failed: ' + (err.message || err)
    stopCamera()
  }
})
// end capture button guard

async function captureFromVideoToCanvas(){
  const video = cameraVideo
  // compute guide box relative to displayed video and map to video pixel coords
  const videoRect = video.getBoundingClientRect()
  const guide = document.getElementById('guideBox')
  const guideRect = guide.getBoundingClientRect()

  const left = Math.max(0, guideRect.left - videoRect.left)
  const top = Math.max(0, guideRect.top - videoRect.top)
  const clientW = videoRect.width || video.videoWidth || 1280
  const clientH = videoRect.height || video.videoHeight || 720
  const ratioX = (video.videoWidth || clientW) / clientW
  const ratioY = (video.videoHeight || clientH) / clientH

  const srcX = Math.round(left * ratioX)
  const srcY = Math.round(top * ratioY)
  const srcW = Math.round(guideRect.width * ratioX)
  const srcH = Math.round(guideRect.height * ratioY)

  // fallback to full frame if calculations are invalid
  if (srcW <= 10 || srcH <= 10){
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    await sendCanvasBlob(canvas)
    return
  }

  const scale = 1.2 // zoom slightly
  const outW = Math.min(1400, Math.round(srcW * scale))
  const outH = Math.round(srcH * scale)
  const canvas = document.createElement('canvas')
  canvas.width = outW
  canvas.height = outH
  const ctx = canvas.getContext('2d')
  ctx.drawImage(video, srcX, srcY, srcW, srcH, 0, 0, outW, outH)
  await sendCanvasBlob(canvas)
}

async function captureBitmapAndCrop(bitmap){
  const video = cameraVideo
  const videoRect = video.getBoundingClientRect()
  const guide = document.getElementById('guideBox')
  const guideRect = guide.getBoundingClientRect()

  const left = Math.max(0, guideRect.left - videoRect.left)
  const top = Math.max(0, guideRect.top - videoRect.top)
  const clientW = videoRect.width || bitmap.width
  const clientH = videoRect.height || bitmap.height
  const ratioX = bitmap.width / clientW
  const ratioY = bitmap.height / clientH

  const srcX = Math.round(left * ratioX)
  const srcY = Math.round(top * ratioY)
  const srcW = Math.round(guideRect.width * ratioX)
  const srcH = Math.round(guideRect.height * ratioY)

  if (srcW <= 10 || srcH <= 10){
    // fallback: draw full bitmap
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(bitmap, 0, 0)
    await sendCanvasBlob(canvas)
    return
  }

  const scale = 1.2
  const outW = Math.min(1400, Math.round(srcW * scale))
  const outH = Math.round(srcH * scale)
  const canvas = document.createElement('canvas')
  canvas.width = outW
  canvas.height = outH
  const ctx = canvas.getContext('2d')
  ctx.drawImage(bitmap, srcX, srcY, srcW, srcH, 0, 0, outW, outH)
  await sendCanvasBlob(canvas)
}

async function sendCanvasBlob(canvas){
  return new Promise((resolve, reject)=>{
    canvas.toBlob(async (blob)=>{
      if (!blob){ messages.textContent = 'Capture failed'; reject(new Error('no blob')); return }
      // Store the captured blob locally and show a preview; do not auto-upload.
      lastCapturedBlob = blob
      const url = URL.createObjectURL(blob)
      capturePreview.src = url
      capturePreview.style.display = 'inline-block'
      // no auto-upload; show small preview only
      // show retake button and update label
      if (retakeBtn) retakeBtn.style.display = 'inline-block'
      fileNameSpan.textContent = 'Captured image'
      fileLabel.textContent = 'Change image'
      // stop camera but keep preview
      stopCamera()
      resolve({success:true})
    }, 'image/jpeg', 0.9)
  })
}

function stopCamera(){
  if (cameraStream){
    cameraStream.getTracks().forEach(t=>t.stop())
    cameraStream = null
  }
  cameraContainer.style.display = 'none'
}

// Retake flow: clear captured blob, hide preview, re-open camera
if (retakeBtn){
  retakeBtn.addEventListener('click', async ()=>{
    lastCapturedBlob = null
    // revoke old object URL if present
    try{ if (capturePreview && capturePreview.src && capturePreview.src.startsWith('blob:')) URL.revokeObjectURL(capturePreview.src) }catch(e){}
    capturePreview.style.display = 'none'
    capturePreview.src = ''
    fileNameSpan.textContent = ''
    fileLabel.textContent = 'Choose image'
    retakeBtn.style.display = 'none'
    // re-open camera
    try{
      cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      cameraVideo.srcObject = cameraStream
      cameraContainer.style.display = 'block'
    }catch(err){
      messages.textContent = 'Could not access camera: ' + err.message
    }
  })
}
// end retake flow

// pre-upload concerns are included in the FormData and saved server-side

// hamburger menu toggle (works on both pages)
function setupMenu(){
  const btn = document.getElementById('hamburgerBtn')
  const menu = document.getElementById('sideMenu')
  const close = document.getElementById('menuClose')
  if (!btn || !menu) return
  btn.addEventListener('click', ()=>{ menu.classList.add('open'); menu.setAttribute('aria-hidden','false') })
  if (close) close.addEventListener('click', ()=>{ menu.classList.remove('open'); menu.setAttribute('aria-hidden','true') })
  // click outside to close
  document.addEventListener('click', (ev)=>{
    if (!menu.classList.contains('open')) return
    const inside = menu.contains(ev.target) || (btn.contains(ev.target))
    if (!inside) { menu.classList.remove('open'); menu.setAttribute('aria-hidden','true') }
  })
}

// init menu on DOMContentLoaded in case script loaded early
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setupMenu)
else setupMenu()
