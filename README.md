# ssh_integration
Custom SSH Intergration for HACS

Support for both switch and sensor options for remote server over ssh.

This integration was made for the purposes of remote POE (Power Over Ethernet) control, and modification may be needed for it to work for other applications.

To get started clone this repository into `/config/`, so that the files are stored at:
```
/config/custom_components/ssh/__init__.py
/config/custom_components/ssh/switch.py
/config/custom_components/ssh/sensor.py
/config/custom_components/ssh/manifest.json
```
## Example Configurations
**Switch**
```yaml
switch:
  - platform: ssh
    command_off: sudo off_command
    command_on: sudo on_command
    command_state: sudo status_command
    host: 127.0.0.1
    name: example_name
    port: 22
    scan_interval: 30
    unique_id: switch_unique_id
    username: example_username
    key: /config/example_key
```
### Configuration Variables
**command_off**

  (string)(Required) Command to turn off the switch
  
**command_on**

  (string)(Required) Command to turn on the switch 

**command_state**

  (string)(Optional) Optional string to check switch state. Run every scan_interval. Overrides optimistic updates.

**scan_interval**

  (int)(Optional) How often to run the command_state command in seconds. Ignored if command_state is None.

**friendly_name**

(string)(Optional) Display name for switch. Will override to the unique_id if none is provided.

**value_template**

(string)(Optional) Value template to pass the return of command_state through before displaying. Following HASS standards, must return a '1' for On.

**icon_template**

(string)(Optional) MDI formatted icon value

**command_timeout**

(int)(Optional) Command timeout for command_state.

**unique_id**

(string)(Required) Unique ID for switch. Required for all switches.

**host**

(string)(Required) Host to connect to. Assumed to be in IP format (ex. 127.0.0.1)

**port**

(int)(Optional) Override for SSH port. Defaults to SSH standard 22.

**name**

(string)(Optional) Alias for friendly_name.

**username**

(string)(Optional) SSH authentication username.

**key**

(string)(Optional) Path to stored ssh key file. Should be of format `/config/path_to_key/key`


**Sensor**
```yaml
sensor:
  - platform: ssh
    command: sudo status_command
    host: 127.0.0.1
    name: example_name
    port: 22
    scan_interval: 5
    unique_id: sensor_unique_id
    username: example_username
    key: /config/example_key
```

**host**

(string)(Required) Host to connect to. Assumed to be in IP format (ex. 127.0.0.1)

**port**

(int)(Optional) Override for SSH port. Defaults to SSH standard 22.

**value_template**

(string)(Optional) Value template to pass the return of command through before displaying. Following HASS standards, must return a '1' for On.

**username**

(string)(Optional) SSH authentication username.

**name**

(string)(Optional) Display name for switch. Will override to the unique_id if none is provided.

**key**

(string)(Optional) Path to stored ssh key file. Should be of format `/config/path_to_key/key`

**command**

(string)(Required) Command to run on the remote server

**unique_id**

(string)(Required) Unique ID for switch. Required for all switches.

## Future Updates
```
- Add support for password authentication instead of key-based auth.
- Add the same options for sensor as there is for switch. Not necessary, but nice for continuity.
```
