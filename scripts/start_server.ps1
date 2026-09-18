$env:PORT = '5003'
$py = 'C:\Users\gugig\AppData\Local\Programs\Python\Python312\python.exe'
$wd = 'C:\Users\gugig\Documents\Projects\song_project'
$p = Start-Process -FilePath $py -ArgumentList 'run.py' -WorkingDirectory $wd -WindowStyle Hidden -PassThru
$p.Id
