FROM public.ecr.aws/lambda/python:3.12
COPY codeemail/main.py ${LAMBDA_TASK_ROOT}/main.py
USER 1000
CMD ["main.lambda_handler"]
