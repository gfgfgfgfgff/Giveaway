import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta, timezone
import random
from typing import Literal

TOKEN = os.getenv('TOKEN')

# 🇫🇷 Fuseau horaire France (UTC+1)
FRANCE_TZ = timezone(timedelta(hours=1))

class GiveawayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True
        intents.guilds = True
        intents.voice_states = True  # Pour vérifier les salons vocaux
        intents.presences = True  # Pour vérifier les statuts
        
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        
        self.active_giveaways = {}
        self.authorized_users = set()
        self.participants_data = {}  # Stocke les données des participants (vocal, statut, etc.)

    async def setup_hook(self):
        await self.add_cog(GiveawayCog(self))
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} commandes slash synchronisées")
        except Exception as e:
            print(f"❌ Erreur synchronisation: {e}")

    async def on_ready(self):
        print(f"✅ {self.user} est connecté !")
        print(f"Latence : {round(self.latency * 1000)}ms")
        
        await self.change_presence(
            activity=discord.Game(
                name="/akusa"
            ),
            status=discord.Status.dnd
        )
        
        print(f"📊 Présence : 🔴 Ne pas déranger - Joue à /akusa")

class GiveawayView(discord.ui.View):
    """View pour le bouton de participation"""
    
    def __init__(self, emoji: str, end_time: datetime, winners: int, prize: str, channel_id: int, message_id: int = None, conditions_type: str = None):
        super().__init__(timeout=None)
        self.emoji = emoji
        self.end_time = end_time
        self.winners = winners
        self.prize = prize
        self.channel_id = channel_id
        self.message_id = message_id
        self.conditions_type = conditions_type  # "nitro" ou "deco" ou None
        self.participants = set()
        self.message = None

        # ✅ Ajout du bouton avec l'emoji
        button = discord.ui.Button(
            style=discord.ButtonStyle.gray,
            label="participer",
            emoji=self.emoji,
            custom_id=f"giveaway_{message_id}" if message_id else None
        )
        button.callback = self.participate_button
        self.add_item(button)

    async def participate_button(self, interaction: discord.Interaction):
        """Bouton de participation - toggle participation"""
        
        if interaction.user.bot:
            await interaction.response.send_message("Les bots ne peuvent pas participer !", ephemeral=True)
            return

        user_id = interaction.user.id
        
        if user_id in self.participants:
            self.participants.remove(user_id)
            await interaction.response.send_message("Vous ne participez plus au giveaway", ephemeral=True)
        else:
            self.participants.add(user_id)
            await interaction.response.send_message("Votre participation est bien enregistrée", ephemeral=True)

        if self.message:
            embed = self.message.embeds[0]
            # 🇫🇷 Heure France (UTC+1)
            france_time = self.end_time.astimezone(FRANCE_TZ)
            embed.set_footer(text=f"Participants: {len(self.participants)} • Fin: {france_time.strftime('%d/%m/%Y %H:%M:%S')}")
            await self.message.edit(embed=embed)

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.check_expired_giveaways())

    async def check_expired_giveaways(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.now(FRANCE_TZ)  # 🇫🇷 Heure France
                expired = []
                
                for message_id, data in self.bot.active_giveaways.items():
                    if current_time >= data["end_time"]:
                        expired.append(message_id)
                
                for message_id in expired:
                    await self.end_giveaway(message_id)
                
                await asyncio.sleep(60)
            except Exception as e:
                print(f"Erreur check_expired_giveaways: {e}")
                await asyncio.sleep(60)

    @app_commands.command(name="giveaway", description="Lance un giveaway")
    async def giveaway(
        self, 
        interaction: discord.Interaction, 
        gain: str,
        temps: str,
        salon: discord.TextChannel,
        nombre_de_gagnants: app_commands.Range[int, 1, 25],
        emoji: str = "🎉"
    ):
        """Commande slash pour créer un giveaway - Nombre de gagnants OBLIGATOIRE"""
        
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            time_unit = temps[-1].lower()
            time_value = int(temps[:-1])
            
            if time_unit == 's':
                duration = timedelta(seconds=time_value)
            elif time_unit == 'm':
                duration = timedelta(minutes=time_value)
            elif time_unit == 'h':
                duration = timedelta(hours=time_value)
            elif time_unit == 'j':
                duration = timedelta(days=time_value)
            else:
                embed_error = discord.Embed(
                    description="Format de temps invalide. Utilisez `s`, `m`, `h` ou `j`",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed_error, ephemeral=True)
                return

            # 🇫🇷 Heure de fin en France (UTC+1)
            end_time = datetime.now(FRANCE_TZ) + duration

            embed = discord.Embed(
                title="**Giveaway**",
                description=f"```\nGain : {gain}\n\nDurée : {temps}\n\nNombre de gagnants : {nombre_de_gagnants}\n\n```",
                color=0xFFFFFF
            )
            
            embed.add_field(name="\u200b", value="───────────────────", inline=False)
            # 🇫🇷 Affichage heure France
            embed.set_footer(text=f"Participants: 0 • Fin: {end_time.strftime('%d/%m/%Y %H:%M:%S')}")

            view = GiveawayView(emoji, end_time, nombre_de_gagnants, gain, salon.id)
            
            giveaway_message = await salon.send(embed=embed, view=view)
            view.message = giveaway_message
            view.message_id = giveaway_message.id
            
            self.bot.active_giveaways[giveaway_message.id] = {
                "end_time": end_time,
                "winners": nombre_de_gagnants,
                "prize": gain,
                "emoji": emoji,
                "channel_id": salon.id,
                "message_id": giveaway_message.id,
                "host_id": interaction.user.id,
                "view": view,
                "participants": view.participants,
                "conditions_type": None
            }

            embed_confirm = discord.Embed(
                description=f"Le giveaway **{gain}** est lancé dans le salon {salon.mention}",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_confirm, ephemeral=True)

        except ValueError:
            embed_error = discord.Embed(
                description="Format de temps invalide. Exemple: `10s`, `5m`, `2h`, `1j`",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
        except Exception as e:
            embed_error = discord.Embed(
                description=f"Une erreur est survenue: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)

    @app_commands.command(name="pgiveaway", description="Lance un giveaway avec conditions prédéfinies")
    @app_commands.choices(gain=[
        app_commands.Choice(name="Nitro boost", value="nitro"),
        app_commands.Choice(name="Décoration", value="deco")
    ])
    @app_commands.choices(nombre=[
        app_commands.Choice(name="1", value=1),
        app_commands.Choice(name="2", value=2),
        app_commands.Choice(name="3", value=3),
        app_commands.Choice(name="4", value=4),
        app_commands.Choice(name="5", value=5),
        app_commands.Choice(name="6", value=6),
        app_commands.Choice(name="7", value=7),
        app_commands.Choice(name="8", value=8),
        app_commands.Choice(name="9", value=9),
        app_commands.Choice(name="10", value=10),
        app_commands.Choice(name="11", value=11),
        app_commands.Choice(name="12", value=12),
        app_commands.Choice(name="13", value=13),
        app_commands.Choice(name="14", value=14),
        app_commands.Choice(name="15", value=15),
    ])
    async def pgiveaway(
        self, 
        interaction: discord.Interaction, 
        gain: app_commands.Choice[str],
        nombre: app_commands.Choice[int],
        temps: str,
        salon: discord.TextChannel,
        emoji: str = "🎉"
    ):
        """Commande slash pour créer un giveaway personnalisé avec conditions"""
        
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            time_unit = temps[-1].lower()
            time_value = int(temps[:-1])
            
            if time_unit == 's':
                duration = timedelta(seconds=time_value)
            elif time_unit == 'm':
                duration = timedelta(minutes=time_value)
            elif time_unit == 'h':
                duration = timedelta(hours=time_value)
            elif time_unit == 'j':
                duration = timedelta(days=time_value)
            else:
                embed_error = discord.Embed(
                    description="Format de temps invalide. Utilisez `s`, `m`, `h` ou `j`",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed_error, ephemeral=True)
                return

            # Déterminer le libellé du gain
            gain_label = "NITRO BOOST" if gain.value == "nitro" else "DECORATION"
            gain_display = "Nitro boost" if gain.value == "nitro" else "Décoration"
            
            # 🇫🇷 Heure de fin en France (UTC+1)
            end_time = datetime.now(FRANCE_TZ) + duration

            embed = discord.Embed(
                title="**Giveaway**",
                description=f"```\nGain : {gain_display}\n\nDurée : {temps}\n\nNombre de gagnants : {nombre.value}\n\n```",
                color=0xFFFFFF
            )
            
            embed.add_field(name="\u200b", value="───────────────────", inline=False)
            # 🇫🇷 Affichage heure France
            embed.set_footer(text=f"Participants: 0 • Fin: {end_time.strftime('%d/%m/%Y %H:%M:%S')}")

            view = GiveawayView(emoji, end_time, nombre.value, gain_display, salon.id, conditions_type=gain.value)
            
            # Envoi de l'embed principal
            giveaway_message = await salon.send(embed=embed, view=view)
            view.message = giveaway_message
            view.message_id = giveaway_message.id
            
            # Déterminer le message de conditions selon le gain et le nombre
            conditions_message = ""
            role_id = "<@&1466923187534303444>"
            
            # Construction du message de base
            if nombre.value == 1 or nombre.value == 2:
                # X1 et X2 : mention rôle seulement
                condition_vocale = "`-` Etre en vocal **du debut a la fin**"
                mention = role_id
                here = ""
            elif 3 <= nombre.value <= 10:
                # X3 à X10 : mention rôle + @here + condition "demute"
                condition_vocale = "`-` Etre en vocal **du debut a la fin** en etant **demute**"
                mention = role_id
                here = "@here"
            else:
                # X11 à X15 : mention rôle + @here + condition "demute et avec d'autres membres"
                condition_vocale = "`-` Etre en vocal **du debut a la fin** en etant **demute** **etre avec d'autres membres**"
                mention = role_id
                here = "@here"
            
            # Construction du message complet
            conditions_message = f"""# {gain_label} X{nombre.value}
Condition : {mention} {here}

{condition_vocale}

`-` Avoir `/akusa` **en status** du __debut__ a la __fin__


__Sa ne sert a rien de se connecter a la fin, on vois tout grace au logs__"""
            
            # Envoi du message de conditions
            await salon.send(conditions_message)
            
            self.bot.active_giveaways[giveaway_message.id] = {
                "end_time": end_time,
                "winners": nombre.value,
                "prize": gain_display,
                "emoji": emoji,
                "channel_id": salon.id,
                "message_id": giveaway_message.id,
                "host_id": interaction.user.id,
                "view": view,
                "participants": view.participants,
                "conditions_type": gain.value,
                "conditions_level": nombre.value
            }

            embed_confirm = discord.Embed(
                description=f"Le giveaway **{gain_display}** est lancé dans le salon {salon.mention} avec conditions",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_confirm, ephemeral=True)

        except ValueError:
            embed_error = discord.Embed(
                description="Format de temps invalide. Exemple: `10s`, `5m`, `2h`, `1j`",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
        except Exception as e:
            embed_error = discord.Embed(
                description=f"Une erreur est survenue: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)

    @app_commands.command(name="reroll", description="Choisit de nouveaux gagnants pour un giveaway")
    async def reroll(self, interaction: discord.Interaction, id_du_message: str):
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            message_id = int(id_du_message)
        except ValueError:
            embed_error = discord.Embed(
                description="Id du message invalide",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        message = None
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(message_id)
                    break
                except:
                    continue

        if not message:
            embed_error = discord.Embed(
                description="Message non trouvé. Vérifiez l'ID.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        await self.select_winners(message, interaction, reroll=True)

    @app_commands.command(name="autorise", description="Autorise un utilisateur aux commandes giveaway")
    async def autorise(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.administrator:
            embed_error = discord.Embed(
                description="Seuls les administrateurs peuvent utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        self.bot.authorized_users.add(user.id)
        
        embed_success = discord.Embed(
            description=f"{user.mention} est maintenant autorisé à utiliser les commandes giveaway.",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed_success, ephemeral=True)

    async def end_giveaway(self, message_id: int):
        try:
            if message_id not in self.bot.active_giveaways:
                return

            data = self.bot.active_giveaways[message_id]
            channel = self.bot.get_channel(data["channel_id"])
            
            if not channel:
                return
                
            try:
                message = await channel.fetch_message(message_id)
            except:
                del self.bot.active_giveaways[message_id]
                return

            await self.select_winners(message)
            
        except Exception as e:
            print(f"Erreur end_giveaway: {e}")

    async def check_conditions(self, user, conditions_type, conditions_level):
        """Vérifie si un utilisateur respecte les conditions"""
        
        # Vérifier le statut /akusa
        has_akusa = False
        for activity in user.activities:
            if activity.type == discord.ActivityType.custom and activity.name and "/akusa" in activity.name:
                has_akusa = True
                break
        
        if not has_akusa:
            return False, "pas le statut /akusa"
        
        # Vérifier la présence en vocal
        if not user.voice or not user.voice.channel:
            return False, "pas en vocal"
        
        # Vérifier les conditions selon le niveau
        if conditions_level >= 3:
            # Être démuté
            if user.voice.self_mute or user.voice.mute:
                return False, "muet"
        
        if conditions_level >= 11:
            # Être avec d'autres membres (au moins 1 autre personne)
            if len(user.voice.channel.members) < 2:
                return False, "seul dans le vocal"
        
        return True, "conditions respectées"

    async def select_winners(self, message: discord.Message, interaction: discord.Interaction = None, reroll: bool = False):
        message_id = message.id
        
        if message_id not in self.bot.active_giveaways and not reroll:
            return

        if not reroll:
            data = self.bot.active_giveaways[message_id]
        else:
            embed = message.embeds[0]
            description = embed.description
            
            gain_line = [line for line in description.split('\n') if 'Gain :' in line][0]
            gain = gain_line.replace('Gain :', '').strip()
            
            winners_line = [line for line in description.split('\n') if 'Nombre de gagnants :' in line][0]
            winners_count = int(winners_line.replace('Nombre de gagnants :', '').strip())
            
            emoji = "🎉"
            if message.components and message.components[0].children:
                emoji = message.components[0].children[0].emoji or "🎉"
            
            data = {
                "winners": winners_count,
                "prize": gain,
                "emoji": emoji,
                "host_id": None,
                "conditions_type": None,
                "conditions_level": None
            }

        winners_count = data["winners"]
        prize = data["prize"]
        emoji = data.get("emoji", "🎉")
        host_id = data.get("host_id")
        conditions_type = data.get("conditions_type")
        conditions_level = data.get("conditions_level")

        participants = []
        
        if not reroll and message_id in self.bot.active_giveaways:
            view = data.get("view")
            if view and hasattr(view, 'participants'):
                for user_id in view.participants:
                    user = self.bot.get_user(user_id)
                    if user:
                        participants.append(user)
        else:
            for reaction in message.reactions:
                if str(reaction.emoji) == emoji:
                    async for user in reaction.users():
                        if not user.bot:
                            participants.append(user)
                    break

        if len(participants) < winners_count:
            # Cas 4 : Pas assez de participants
            ping_message = f"Pas assez de participants pour le giveaway **{prize}**."
            
            # Modifier l'embed
            new_embed = discord.Embed(
                title=f"**Giveaway ({prize}) terminé**",
                color=0xFFFFFF
            )
            new_embed.add_field(name="**Résultat**", value="Pas assez de participants", inline=False)
            new_embed.set_footer(text=f"Total participants: {len(participants)} • Giveaway terminé")
            
            await message.edit(embed=new_embed, view=None)
            await message.reply(ping_message)
            
            # Mentionner l'hôte et supprimer après 2 secondes
            if host_id:
                host = self.bot.get_user(host_id)
                if host:
                    host_mention = await message.channel.send(f"{host.mention}")
                    await asyncio.sleep(2)
                    await host_mention.delete()
            
            if not reroll and message_id in self.bot.active_giveaways:
                del self.bot.active_giveaways[message_id]
            return

        # Sélectionner les gagnants
        selected_winners = random.sample(participants, min(winners_count, len(participants)))
        
        winners_valid = []
        winners_invalid = []
        
        # Vérifier les conditions pour chaque gagnant (si c'est un pgiveaway)
        if conditions_type:
            for winner in selected_winners:
                # Récupérer le membre (pas seulement l'user)
                member = message.guild.get_member(winner.id)
                if member:
                    valid, reason = await self.check_conditions(member, conditions_type, conditions_level)
                    if valid:
                        winners_valid.append(winner)
                    else:
                        winners_invalid.append(winner)
                else:
                    winners_invalid.append(winner)
        else:
            # Pas de conditions, tous les gagnants sont valides
            winners_valid = selected_winners

        # Construire le message selon les cas
        valid_mentions = " ".join([w.mention for w in winners_valid])
        invalid_mentions = " ".join([w.mention for w in winners_invalid])
        
        if winners_valid and not winners_invalid:
            # Cas 1 : Tous valides
            ping_message = f"{valid_mentions} ont gagné **{prize}** !"
        elif winners_valid and winners_invalid:
            # Cas 2 : Certains valides, d'autres non
            ping_message = f"{valid_mentions} ont gagné **{prize}**\n{invalid_mentions} ont gagné mais n'ont pas les conditions requises"
        elif not winners_valid and winners_invalid:
            # Cas 3 : Aucun valide
            ping_message = f"{invalid_mentions} ont gagné **{prize}** mais il ont pas les condition requises"
        else:
            ping_message = f"Personne n'a gagné **{prize}**"

        # Modifier l'embed original
        new_embed = discord.Embed(
            title=f"**Giveaway ({prize}) terminé**",
            color=0xFFFFFF
        )
        
        result_text = f"**Gagnants valides :** {len(winners_valid)}\n**Gagnants non valides :** {len(winners_invalid)}"
        new_embed.add_field(name="**Résultat**", value=result_text, inline=False)
        new_embed.set_footer(text=f"Total participants: {len(participants)} • Giveaway terminé")

        # Supprimer le bouton
        await message.edit(embed=new_embed, view=None)
        
        # Envoyer le message de résultat
        result_message = await message.reply(ping_message)
        
        # Message de vérification pour chaque gagnant valide
        for winner in winners_valid:
            member = message.guild.get_member(winner.id)
            if member:
                # Récupérer le statut personnalisé
                status_text = "pas de statut"
                for activity in member.activities:
                    if activity.type == discord.ActivityType.custom:
                        if activity.name:
                            status_text = activity.name
                        break
                
                # Vérifier si en vocal
                if member.voice and member.voice.channel:
                    check_message = f"{member.mention} est en vocal dans {member.voice.channel.mention} et il a `{status_text}` en status !"
                else:
                    check_message = f"{member.mention} n'est pas en vocal et il a `{status_text}` en status !"
                
                await message.channel.send(check_message)

        # Mentionner l'hôte et supprimer après 2 secondes
        if host_id:
            host = self.bot.get_user(host_id)
            if host:
                host_mention = await message.channel.send(f"{host.mention}")
                await asyncio.sleep(2)
                await host_mention.delete()

        if not reroll and message_id in self.bot.active_giveaways:
            del self.bot.active_giveaways[message_id]

        if interaction:
            embed_success = discord.Embed(
                description=f"Nouveau{'x' if winners_count > 1 else ''} gagnant{'s' if winners_count > 1 else ''} sélectionné{'s' if winners_count > 1 else ''} !",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_success, ephemeral=True)

bot = GiveawayBot()

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("❌ Erreur: Token invalide")
        except Exception as e:
            print(f"❌ Erreur de démarrage: {e}")
    else:
        print("❌ Erreur: Token non trouvé")