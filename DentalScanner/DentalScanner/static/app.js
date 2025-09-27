const fileInput = document.getElementById('fileInput')
const uploadBtn = document.getElementById('uploadBtn')
const messages = document.getElementById('messages')
const resultDiv = document.getElementById('result')
const resultImg = document.getElementById('resultImg')
const cameraBtn = document.getElementById('cameraBtn')
const cameraContainer = document.getElementById('cameraContainer')
const cameraVideo = document.getElementById('cameraVideo')
const captureBtn = document.getElementById('captureBtn')
const cancelCameraBtn = document.getElementById('cancelCameraBtn')
let cameraStream = null

uploadBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  if (!fileInput.files || fileInput.files.length === 0){
    messages.textContent = 'Select a file first.'
    return
  }
  const f = fileInput.files[0]
  const fd = new FormData()
  fd.append('image', f)
  // include pre-upload concern if provided
  const preConcern = (document.getElementById('concernText')||{value:''}).value.trim()
  if (preConcern) fd.append('concern', preConcern)

  uploadBtn.disabled = true
  uploadBtn.textContent = 'Uploading...'

  try{
    const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
    const data = await res.json()
    if (!data.success){
      messages.textContent = data.error || 'Upload failed'
      uploadBtn.disabled = false
      uploadBtn.textContent = 'Upload and Scan'
      return
    }
  // show the result image
  resultImg.src = data.result_url + '?_=' + Date.now()
  // store uploaded filename for reference
  resultDiv.dataset.uploadedFilename = data.uploaded_filename || ''
  resultDiv.style.display = 'block'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }catch(err){
    messages.textContent = err.message || 'Network error'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }
})

// Camera flow
cameraBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  try{
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    cameraVideo.srcObject = cameraStream
    cameraContainer.style.display = 'block'
  }catch(err){
    messages.textContent = 'Could not access camera: ' + err.message
  }
})

cancelCameraBtn.addEventListener('click', ()=>{
  stopCamera()
})

captureBtn.addEventListener('click', async ()=>{
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
  const fd = new FormData()
  fd.append('image', blob, 'capture.jpg')
  const preConcern = (document.getElementById('concernText')||{value:''}).value.trim()
  if (preConcern) fd.append('concern', preConcern)
      uploadBtn.disabled = true
      uploadBtn.textContent = 'Uploading...'
      try{
        const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
        const data = await res.json()
    if (!data.success){ messages.textContent = data.error || 'Upload failed'; resolve(data); return }
  resultImg.src = data.result_url + '?_=' + Date.now()
  resultDiv.dataset.uploadedFilename = data.uploaded_filename || ''
        resultDiv.style.display = 'block'
        resolve(data)
      }catch(err){
        messages.textContent = err.message || 'Network error'
        reject(err)
      }finally{
        uploadBtn.disabled = false
        uploadBtn.textContent = 'Upload and Scan'
        stopCamera()
      }
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
