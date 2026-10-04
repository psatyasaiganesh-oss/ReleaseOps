output "instance_id" {
  value = aws_instance.lab.id
}

output "public_ip" {
  value = aws_instance.lab.public_ip
}

output "ssh_tunnel_command" {
  value = "ssh -i YOUR_KEY.pem -L 18081:127.0.0.1:18081 -L 18080:127.0.0.1:18080 ec2-user@${aws_instance.lab.public_ip}"
}
