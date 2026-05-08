# FinTrack — backend                                                                                                                 
                                                                                                                                       
  FastAPI-приложение для учёта личных финансов.                   

  ## Локальный запуск                                                                                                                  
   
  ```powershell                                                                                                                        
  # Из корня репозитория                                          
  cd backend
  py -m venv .venv                                                                                                                     
  .\.venv\Scripts\Activate.ps1
  pip install --upgrade pip                                                                                                            
  pip install "fastapi[standard]"                                 
  fastapi dev app/main.py
  ```                                                                                                                                  
   
  После запуска:                                                                                                                       
  - API: http://localhost:8000                                    
  - Swagger UI (интерактивная документация): http://localhost:8000/docs                                                                
  - ReDoc: http://localhost:8000/redoc
  - Health check: http://localhost:8000/health                                                                                         
                                                                  
  ## Структура                                                                                                                         
                                                                  
  ```                                                                                                                                  
  backend/                                                        
  ├── app/
  │   ├── __init__.py
  │   └── main.py        # точка входа FastAPI, регистрация роутов
  ├── pyproject.toml     # метаданные пакета и зависимости                                                                             
  └── README.md
  ```