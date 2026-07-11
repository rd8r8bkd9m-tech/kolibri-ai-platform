use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RoleId {
    Client,
    ClientPro,
    Operator,
    ServerAdmin,
    Developer,
    Owner,
}

impl RoleId {
    pub fn parse(value: &str) -> Self {
        match value {
            "client_pro" => Self::ClientPro,
            "operator" => Self::Operator,
            "server_admin" => Self::ServerAdmin,
            "developer" => Self::Developer,
            "owner" => Self::Owner,
            _ => Self::Client,
        }
    }

    pub fn allowed_apps(self) -> &'static [&'static str] {
        match self {
            Self::Client | Self::ClientPro => &["home", "estimate", "documents", "settings"],
            Self::Operator => &["home", "factory", "settings"],
            Self::ServerAdmin => &["home", "servers", "factory", "settings"],
            Self::Developer => &["home", "developer", "settings"],
            Self::Owner => &["home", "estimate", "documents", "factory", "servers", "developer", "settings"],
        }
    }

    pub fn can_open(self, app_id: &str) -> bool {
        self.allowed_apps().contains(&app_id)
    }

    pub fn can_execute_dangerous_action(self) -> bool {
        false
    }

    pub fn requires_approval(self, capability: &str) -> bool {
        capability.starts_with("deploy.")
            || capability.starts_with("server.mutate")
            || capability.starts_with("keys.rotate")
            || capability.starts_with("git.merge")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn client_never_sees_admin_apps() {
        let role = RoleId::ClientPro;
        assert!(role.can_open("estimate"));
        assert!(!role.can_open("factory"));
        assert!(!role.can_open("servers"));
        assert!(!role.can_open("developer"));
    }

    #[test]
    fn owner_sees_full_product_surface_but_dangerous_actions_stay_gated() {
        let role = RoleId::Owner;
        assert!(role.can_open("factory"));
        assert!(role.can_open("servers"));
        assert!(role.can_open("developer"));
        assert!(!role.can_execute_dangerous_action());
        assert!(role.requires_approval("server.mutate.reboot"));
    }
}
