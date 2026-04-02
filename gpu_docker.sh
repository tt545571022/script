user=tjl
name=vllm-glm
image=vllm/vllm-openai:v0.17.1

docker run -itd --privileged \
  -u root \
	-w /home/${user} \
	--hostname=${name} \
	-e LANG=en_US.UTF-8 \
	-e LANGUAGE=en_US:en \
  --gpus all \
  --net=host \
  --shm-size=50g \
  --name ${user}-${name} \
  --entrypoint "" \
  -v /home/tjl:/home/tjl \
  -v /var/ai-model/:/var/ai-model/ \
  ${image} \
  bash -c "tail -f /dev/null"
