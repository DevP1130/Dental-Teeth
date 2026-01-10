const fileInput = document.getElementById('fileInput')
const uploadBtn = document.getElementById('uploadBtn')
const messages = document.getElementById('messages')
const resultDiv = document.getElementById('result')
const resultImg = document.getElementById('resultImg')
const aiSummaryDiv = document.getElementById('aiSummary')
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
let currentAISummary = '' // Store AI summary text for email

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
  uploadBtn.disabled = true
  uploadBtn.textContent = 'Processing...'
  messages.textContent = 'Uploading and processing image...'
  try{
    const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
    const data = await res.json()
    if (!data.success){
      messages.textContent = 'Error: ' + (data.error || 'Upload failed')
      messages.style.color = '#dc2626'
      uploadBtn.disabled = false
      uploadBtn.textContent = 'Upload and Scan'
      return
    }
    messages.textContent = 'Processing complete!'
    messages.style.color = '#16a34a'
  // show the result image
  if (resultImg) resultImg.src = data.result_url + '?_=' + Date.now()
  // store uploaded filename for reference
  if (resultDiv) {
    resultDiv.dataset.uploadedFilename = data.uploaded_filename || ''
    resultDiv.style.display = 'block'
  }
    // display AI summary if present
    const emailReportSection = document.getElementById('emailReportSection')
    if (aiSummaryDiv){
      if (data.ai_summary){
        // Store AI summary text for email
        currentAISummary = data.ai_summary
        // Format the summary with better styling - preserve line breaks
        const formattedSummary = data.ai_summary.replace(/\n/g, '<br>')
        aiSummaryDiv.innerHTML = '<h3 style="margin-top:0; margin-bottom:12px; color:#020617; font-size:18px;">AI Analysis</h3><div style="color:#475569; line-height:1.6; white-space:pre-wrap;">' + escapeHtml(data.ai_summary).replace(/\n/g, '<br>') + '</div>'
        aiSummaryDiv.style.display = 'block'
        // Show the "Next" button after AI summary is displayed
        if (emailReportSection) emailReportSection.style.display = 'block'
      } else if (data.ai_summary_error){
        currentAISummary = '' // No AI summary available
        aiSummaryDiv.innerHTML = '<h3 style="margin-top:0; margin-bottom:12px; color:#020617;">AI Analysis</h3><div style="color:#dc2626;">' + escapeHtml(data.ai_summary_error) + '</div>'
        aiSummaryDiv.style.display = 'block'
        // Still show Next button even if AI summary failed
        if (emailReportSection) emailReportSection.style.display = 'block'
      } else {
        currentAISummary = ''
        aiSummaryDiv.style.display = 'none'
        aiSummaryDiv.innerHTML = ''
        if (emailReportSection) emailReportSection.style.display = 'none'
      }
    } else {
      if (emailReportSection) emailReportSection.style.display = 'none'
    }
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }catch(err){
    messages.textContent = 'Error: ' + (err.message || 'Network error')
    messages.style.color = '#dc2626'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }
})

// show selected filename when user picks a file
if (fileInput){
  fileInput.addEventListener('change', ()=>{
    const f = (fileInput.files && fileInput.files[0])
    if (f){
      fileNameSpan.textContent = f.name
      fileLabel.textContent = 'Change File'
    } else {
      fileNameSpan.textContent = 'No file selected'
      fileLabel.textContent = 'Choose File'
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
      // Show preview if element exists
      if (capturePreview) {
        capturePreview.src = url
        const previewContainer = document.getElementById('capturePreviewContainer')
        if (previewContainer) previewContainer.style.display = 'block'
      }
      // show retake button and update label
      if (retakeBtn) retakeBtn.style.display = 'inline-block'
      if (fileNameSpan) fileNameSpan.textContent = 'Captured image'
      if (fileLabel) fileLabel.textContent = 'Change image'
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
    if (capturePreview) {
      capturePreview.src = ''
      const previewContainer = document.getElementById('capturePreviewContainer')
      if (previewContainer) previewContainer.style.display = 'none'
    }
    if (fileNameSpan) fileNameSpan.textContent = 'No file selected'
    if (fileLabel) fileLabel.textContent = 'Choose File'
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

// Email report functionality
const sendReportBtn = document.getElementById('sendReportBtn')
const emailStatus = document.getElementById('emailStatus')

if (sendReportBtn) {
  sendReportBtn.addEventListener('click', async () => {
    // Get emails from sessionStorage
    const patientEmail = sessionStorage.getItem('openwide_patient_email')
    const doctorEmail = sessionStorage.getItem('openwide_doctor_email')
    
    if (!patientEmail || !doctorEmail) {
      emailStatus.textContent = 'Error: Patient and doctor emails not found. Please start over from the welcome page.'
      emailStatus.style.color = '#dc2626'
      emailStatus.style.display = 'block'
      return
    }
    
    // Use stored AI summary text
    const aiSummaryText = currentAISummary || (aiSummaryDiv ? aiSummaryDiv.innerText || aiSummaryDiv.textContent : '')
    
    // Disable button and show loading state
    sendReportBtn.disabled = true
    sendReportBtn.textContent = 'Sending Report...'
    emailStatus.textContent = 'Sending email report to patient and doctor...'
    emailStatus.style.color = '#475569'
    emailStatus.style.display = 'block'
    
    try {
      const response = await fetch('/send-report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({
          patient_email: patientEmail,
          doctor_email: doctorEmail,
          ai_summary: aiSummaryText
        })
      })
      
      const data = await response.json()
      
      if (data.success) {
        emailStatus.textContent = '✓ Report sent successfully to ' + patientEmail + ' and ' + doctorEmail
        emailStatus.style.color = '#16a34a'
        sendReportBtn.textContent = 'Report Sent ✓'
        sendReportBtn.style.backgroundColor = '#16a34a'
      } else {
        emailStatus.textContent = 'Error: ' + (data.error || 'Failed to send email report')
        emailStatus.style.color = '#dc2626'
        sendReportBtn.disabled = false
        sendReportBtn.textContent = 'Next - Send Report via Email'
      }
    } catch (err) {
      emailStatus.textContent = 'Error: ' + (err.message || 'Network error while sending report')
      emailStatus.style.color = '#dc2626'
      sendReportBtn.disabled = false
      sendReportBtn.textContent = 'Next - Send Report via Email'
    }
  })
}