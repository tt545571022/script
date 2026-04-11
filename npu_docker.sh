#! /bin/bash
user=tjl
name=vllm-180
# image=vllm-ascend-ucm:v0.9.2rc1
# image=m.daocloud.io/quay.io/ascend/vllm-ascend:glm5
image=quay.io/ascend/vllm-ascend:nightly-releases-v0.18.0
# image=quay.io/ascend/vllm-ascend:releases-v0.18.0
# image=swr.cn-south-1.myhuaweicloud.com/ascendhub/mindie:2.2.RC1-800I-A2-py311-openeuler24.03-lts

docker run -itd -u root \
	--shm-size=500g \
	-w /home/${user} \
	--hostname=${name} \
	-e LANG=en_US.UTF-8 \
	-e LANGUAGE=en_US:en \
--ipc=host \
--net=host \
--device=/dev/davinci0 \
--device=/dev/davinci1 \
--device=/dev/davinci2 \
--device=/dev/davinci3 \
--device=/dev/davinci4 \
--device=/dev/davinci5 \
--device=/dev/davinci6 \
--device=/dev/davinci7 \
--device=/dev/davinci8 \
--device=/dev/davinci9 \
--device=/dev/davinci10 \
--device=/dev/davinci11 \
--device=/dev/davinci12 \
--device=/dev/davinci13 \
--device=/dev/davinci14 \
--device=/dev/davinci15 \
--device=/dev/davinci_manager \
--device=/dev/devmm_svm \
--device=/dev/hisi_hdc \
-v /etc/localtime:/etc/localtime \
-v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
-v /var/log/npu/:/usr/slog \
-v /usr/local/bin/npu-smi:/usr/local/bin/npu-smi \
-v /home/tjl:/home/tjl \
-v /data:/data \
-v /data2/weights:/data2/weights \
-v /usr/local/sbin/:/ust/local/sbin/ \
-v /usr/loacal/Ascend/add-ons/:/usr/local/Ascend/add-ons \
-v /usr/local/sbin/:/usr/local/sbin \
-v /etc/hccn.conf:/etc/hccn.conf \
--privileged \
--name ${user}-${name} \
${image} \
/bin/bash
